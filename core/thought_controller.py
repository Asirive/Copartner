"""
Thought Controller for Asirive Copartner
==========================================
The System 2 reasoning loop. Wraps Gemini in a recursive state machine that
streams output, detects XML tool tags, executes them, and loops until it
reaches a <final_answer> tag or hits the convergence limit.

State machine:
    IDLE → THINKING → ACTING → REFLECTING → ANSWERING → IDLE

Convergence pressure (inspired by Eidos predictive_coder surprise signal):
    Step 7:  Inject a nudge ("Please wrap up and provide your final answer")
    Step 12: Hard-stop — force final answer from whatever Gemini has produced

Usage:
    controller = ThoughtController.create()   # factory: wires all dependencies
    answer = controller.run("Build a landing page for my coffee shop, Beanery.")
    print(answer)
"""

import os
import re
import logging
import yaml
from enum import Enum, auto
from pathlib import Path
from typing import Optional, Generator

logger = logging.getLogger("Copartner.ThoughtController")

PROJECT_ROOT   = Path(__file__).parent.parent
SYSTEM_YAML    = PROJECT_ROOT / "config" / "prompts" / "system.yaml"

MAX_STEPS            = 12
SOFT_CONVERGENCE_AT  = 7


class State(Enum):
    IDLE       = auto()
    THINKING   = auto()
    ACTING     = auto()
    REFLECTING = auto()
    ANSWERING  = auto()


class ThoughtController:
    """
    Recursive System 2 reasoning loop for Asirive Copartner.

    Streams Gemini output, intercepts XML tool tags, executes them via
    ToolExecutor, injects results back into context, and loops until
    a <final_answer> is produced or the step limit is reached.
    """

    def __init__(
        self,
        gemini_client,
        tool_executor,
        memory_manager=None,
        intent_router=None,
        token_budget=None,
        skill_learner=None,
        behavioral_engine=None,
    ):
        self.gemini   = gemini_client
        self.tools    = tool_executor
        self.memory   = memory_manager
        self.router   = intent_router
        self.budget   = token_budget
        self.learner  = skill_learner
        self.behavior = behavioral_engine

        self._system_prompt, self._nudge_prompt, self._force_prompt = self._load_prompts()
        self.state = State.IDLE
        logger.info("ThoughtController initialized")

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def create(cls, api_key: str | None = None) -> "ThoughtController":
        """
        Convenience factory: instantiate and wire all dependencies.
        Reads GEMINI_API_KEY from environment if not provided.
        """
        from core.gemini_client    import GeminiClient
        from core.tool_executor    import ToolExecutor
        from core.token_budget     import TokenBudget
        from core.intent_router    import IntentRouter
        from core.skill_learner    import SkillLearner
        from memory.memory_manager import MemoryManager
        from memory.embeddings     import GeminiEmbedder, make_chromadb_embedding_fn
        from memory.behavioral_engine import BehavioralEngine

        key    = api_key or os.environ.get("GEMINI_API_KEY")
        client = GeminiClient(api_key=key)

        # Wire Gemini embeddings into ChromaDB memory
        embedder    = GeminiEmbedder(client)
        embed_fn    = make_chromadb_embedding_fn(embedder)
        memory      = MemoryManager(embedding_fn=embed_fn)

        budget   = TokenBudget()
        router   = IntentRouter()
        behavior = BehavioralEngine()
        tools    = ToolExecutor(memory_manager=memory, gemini_client=client)
        learner  = SkillLearner(memory_manager=memory)

        return cls(
            gemini_client=client,
            tool_executor=tools,
            memory_manager=memory,
            intent_router=router,
            token_budget=budget,
            skill_learner=learner,
            behavioral_engine=behavior,
        )

    # ── Prompt loading ────────────────────────────────────────────────────────

    def _load_prompts(self) -> tuple[str, str, str]:
        """Load system prompt and convergence prompts from YAML."""
        try:
            data = yaml.safe_load(SYSTEM_YAML.read_text(encoding="utf-8"))
            system  = data.get("system_prompt", "You are Copartner, an AI partner.")
            nudge   = data.get("convergence_nudge", "Please wrap up and write your <final_answer>.")
            force   = data.get("convergence_force", "Write your <final_answer> now.")
            return system, nudge, force
        except Exception as e:
            logger.warning(f"Could not load system.yaml: {e}. Using defaults.")
            return (
                "You are Copartner, an ambient AI partner built by Asirive. "
                "Always respond using XML tags. End with <final_answer>.",
                "Please wrap up and write your <final_answer> tag now.",
                "FINAL STEP: Write your <final_answer> immediately.",
            )

    # ── Context building ──────────────────────────────────────────────────────

    def _build_system_prompt(self, query: str) -> str:
        """Build the full system prompt with memory context and style profile."""
        parts = [self._system_prompt]

        # Inject relevant memories
        if self.memory:
            context = self.memory.get_context_injection(query)
            if context:
                parts.append("\n" + context)

        # Inject style profile
        if self.behavior:
            style = self.behavior.get_profile_prompt()
            if style:
                parts.append("\n" + style)

        # Inject relevant skill if found
        if self.learner:
            skill_content = self.learner.find_skill(query)
            if skill_content:
                parts.append(
                    f"\n[Relevant skill found — use this as a guide:]\n{skill_content[:800]}"
                )

        return "\n".join(parts)

    # ── Core loop ─────────────────────────────────────────────────────────────

    def run(self, query: str, stream_callback=None) -> str:
        """
        Run the System 2 reasoning loop for a user query.

        Args:
            query:           The user's input.
            stream_callback: Optional callable(token: str) for real-time output.

        Returns:
            The final answer string.
        """
        self.state = State.THINKING
        logger.info(f"ThoughtController: starting loop for: {query[:80]}")

        # Route to best model
        decision  = self.router.route(query) if self.router else None
        use_pro   = decision.use_pro if decision else True
        if decision:
            logger.info(f"IntentRouter: {decision.model.upper()} | {decision.rationale}")

        system_prompt = self._build_system_prompt(query)
        messages      = [{"role": "user", "parts": [query]}]
        trace: list[dict] = []
        final_answer: Optional[str] = None

        for step in range(1, MAX_STEPS + 1):
            logger.info(f"ThoughtController: step {step}/{MAX_STEPS} | state={self.state.name}")

            # Convergence pressure
            current_system = system_prompt
            if step >= MAX_STEPS:
                current_system = system_prompt + "\n\n" + self._force_prompt
                self.state = State.ANSWERING
            elif step >= SOFT_CONVERGENCE_AT:
                nudge = self._nudge_prompt.format(step=step)
                current_system = system_prompt + "\n\n" + nudge

            # Check budget
            if self.budget and not self.budget.can_afford(estimated_tokens=4096):
                logger.warning("Token budget exhausted — returning partial answer")
                return "[Budget limit reached. Please try again tomorrow or upgrade your plan.]"

            # Escalate to Pro if we're looping
            if decision and step >= 4 and decision.model == "flash":
                decision = self.router.escalate(decision, reason=f"step {step} escalation")
                use_pro  = True

            # Call Gemini (streaming)
            accumulated = ""
            try:
                for token in self.gemini.generate_stream(
                    contents=messages,
                    system_instruction=current_system,
                    use_pro=use_pro,
                    temperature=0.7,
                    max_output_tokens=4096,
                ):
                    accumulated += token
                    if stream_callback:
                        stream_callback(token)

            except Exception as e:
                logger.error(f"Gemini API error at step {step}: {e}")
                return f"[Copartner encountered an error: {e}]"

            # Record token usage (rough estimate)
            if self.budget:
                est_tokens = len(accumulated.split()) * 1.3
                self.budget.record_usage(
                    int(est_tokens),
                    model="pro" if use_pro else "flash",
                    task=query[:60],
                )

            logger.debug(f"Step {step} output ({len(accumulated)} chars):\n{accumulated[:200]}")

            # Check for final answer
            final = self.tools.has_final_answer(accumulated)
            if final:
                final_answer = final
                self.state   = State.ANSWERING
                trace.append({"tag": "final_answer", "content": final})

                # Execute any other tools in the response before final_answer
                _, actions = self.tools.process_text(accumulated)
                for action in actions:
                    if action["tag"] != "final_answer":
                        trace.append(action)
                break

            # Execute tool tags, inject results back into conversation
            augmented, actions = self.tools.process_text(accumulated)
            trace.extend(actions)

            if actions:
                self.state = State.ACTING
                # Add Gemini's output + tool results to conversation history
                messages.append({"role": "model", "parts": [accumulated]})
                results_text = "\n".join(
                    f"[{a['tag']} result]: {a['result_preview']}"
                    for a in actions if a.get("result_preview")
                )
                if results_text:
                    messages.append({"role": "user", "parts": [
                        f"Tool execution results:\n{results_text}\n\n"
                        "Continue your reasoning based on these results."
                    ]})
            else:
                # No tools found, no final_answer — add raw output and loop
                messages.append({"role": "model", "parts": [accumulated]})
                messages.append({"role": "user", "parts": [
                    "Please continue. Remember to end with <final_answer>your response</final_answer>."
                ]})
                self.state = State.REFLECTING

        # If we hit MAX_STEPS without a final_answer, extract the last output
        if not final_answer:
            logger.warning(f"ThoughtController: hit MAX_STEPS without <final_answer>")
            if messages and messages[-1]["role"] == "model":
                raw = messages[-1]["parts"][0]
                # Strip tags and return whatever we have
                final_answer = re.sub(r"<[^>]+>", "", raw).strip()
            else:
                final_answer = "I was unable to complete my reasoning in time. Please rephrase your query."

        # Post-loop: save skill if task was complex (>3 tool calls)
        tool_calls = sum(1 for t in trace if t.get("tag") not in ("think", "final_answer"))
        if tool_calls >= 3 and self.learner:
            self.learner.save_skill(query, trace)

        # Save conversation to episodic memory
        if self.memory:
            self.memory.store_conversation(query, final_answer, quality=0.6)

        self.state = State.IDLE
        logger.info(f"ThoughtController: loop complete in {step} steps")
        return final_answer

    # ── Stream helper ─────────────────────────────────────────────────────────

    def stream_run(self, query: str) -> Generator[str, None, None]:
        """
        Generator version of run() that yields tokens in real-time.
        The final answer is yielded as a complete block at the end.
        """
        tokens = []

        def collect(token: str):
            tokens.append(token)

        # run() blocks until done, yielding via callback
        # We yield what we can without blocking — simple implementation for Phase 1
        answer = self.run(query, stream_callback=collect)
        for token in tokens:
            yield token

        # Ensure final answer is yielded if not already in stream
        if answer and answer not in "".join(tokens):
            yield "\n\n" + answer
