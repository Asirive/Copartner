"""
Thought Controller for Asirive Copartner
==========================================
The System 2 reasoning loop. Wraps Gemini in a recursive state machine that
streams output via the Interactions API, detects XML tool tags, executes them,
and loops until <final_answer> or the convergence limit is hit.

INTERACTIONS API UPGRADE:
  - Uses client.interactions.create(stream=True) for real token streaming
  - Stateful conversation via previous_interaction_id (server manages context)
  - No more manual message history list — the API handles it server-side
  - Token usage comes back in the interaction.complete event

State machine:
    IDLE → THINKING → ACTING → REFLECTING → ANSWERING → IDLE

Convergence pressure:
    Step 7:  Inject nudge ("Please wrap up and provide your final answer")
    Step 12: Hard-stop — extract best answer from last response
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

MAX_STEPS           = 12
SOFT_CONVERGENCE_AT = 7


class State(Enum):
    IDLE       = auto()
    THINKING   = auto()
    ACTING     = auto()
    REFLECTING = auto()
    ANSWERING  = auto()


class ThoughtController:
    """
    Recursive System 2 reasoning loop for Asirive Copartner.

    Streams Gemini output via Interactions API, intercepts XML tags,
    executes them via ToolExecutor, injects results back as follow-up
    interactions, and loops until <final_answer> is produced.
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
        from core.opencode_client  import OpenCodeClient
        from core.tool_executor    import ToolExecutor
        from core.token_budget     import TokenBudget
        from core.intent_router    import IntentRouter
        from core.skill_learner    import SkillLearner
        from memory.memory_manager import MemoryManager
        from memory.embeddings     import GeminiEmbedder, make_chromadb_embedding_fn
        from memory.behavioral_engine  import BehavioralEngine
        from action.code_scaffolder    import CodeScaffolder
        from integration.connectors.vercel_connector import VercelConnector
        from integration.connectors.stripe_connector import StripeConnector

        key    = api_key or os.environ.get("GEMINI_API_KEY")
        client = GeminiClient(api_key=key)

        # OpenCode Go — cheap open-source model routing
        opencode = OpenCodeClient()

        embedder   = GeminiEmbedder(client)
        embed_fn   = make_chromadb_embedding_fn(embedder)
        memory     = MemoryManager(embedding_fn=embed_fn)

        budget     = TokenBudget()
        router     = IntentRouter()
        behavior   = BehavioralEngine()
        scaffolder = CodeScaffolder(
            gemini_client=client,
            behavioral_engine=behavior,
            opencode_client=opencode,   # uses Kimi K2.6 first, Gemini fallback
        )
        vercel     = VercelConnector()
        learner    = SkillLearner(memory_manager=memory)
        
        # ScreenObserver for tool execution + ambient mode
        from perception.screen_observer import ScreenObserver, ObserverMode
        screen_obs = ScreenObserver(gemini_client=client, mode=ObserverMode.PASSIVE)
        
        tools      = ToolExecutor(
            memory_manager=memory,
            gemini_client=client,
            code_scaffolder=scaffolder,
            vercel_connector=vercel,
            screen_observer=screen_obs,
        )


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
        try:
            data = yaml.safe_load(SYSTEM_YAML.read_text(encoding="utf-8"))
            return (
                data.get("system_prompt", "You are Copartner, an AI partner."),
                data.get("convergence_nudge", "Please wrap up and write <final_answer>."),
                data.get("convergence_force", "Write <final_answer> immediately."),
            )
        except Exception as e:
            logger.warning(f"Could not load system.yaml: {e}")
            return (
                "You are Copartner, an ambient AI partner. Always end with <final_answer>.",
                "Please wrap up and write <final_answer> now. Step: {step}",
                "FINAL STEP: Write <final_answer> immediately.",
            )

    # ── Context helpers ───────────────────────────────────────────────────────

    def _build_system_prompt(self, query: str) -> str:
        """Assemble the full system prompt with memory + style context injected."""
        parts = [self._system_prompt]
        if self.memory:
            ctx = self.memory.get_context_injection(query)
            if ctx:
                parts.append("\n" + ctx)
        if self.behavior:
            style = self.behavior.get_profile_prompt()
            if style:
                parts.append("\n" + style)
        if self.learner:
            skill = self.learner.find_skill(query)
            if skill:
                parts.append(f"\n[Relevant skill:]\n{skill[:600]}")
        return "\n".join(parts)

    # ── Core loop ─────────────────────────────────────────────────────────────

    def run(self, query: str, stream_callback=None) -> str:
        """
        Run the System 2 reasoning loop using the Interactions API.

        Each step is a new interaction.create() call with previous_interaction_id
        pointing to the last interaction — the server maintains conversation context.

        Args:
            query:           The user's input.
            stream_callback: Optional callable(token: str) for real-time output.

        Returns:
            The final answer string.
        """
        self.state = State.THINKING
        logger.info(f"ThoughtController: starting → '{query[:80]}'")

        # Route to best model
        decision = self.router.route(query) if self.router else None
        use_pro  = decision.use_pro if decision else False
        if decision:
            logger.info(f"Router: {decision.model.upper()} | {decision.rationale}")

        system_prompt = self._build_system_prompt(query)

        # Budget check
        if self.budget and not self.budget.can_afford(estimated_tokens=4096):
            return "[Daily token budget exhausted. Resets tomorrow.]"

        trace:          list[dict] = []
        final_answer:   Optional[str] = None
        interaction_id: Optional[str] = None   # threads the conversation server-side
        current_input   = query

        for step in range(1, MAX_STEPS + 1):
            logger.info(f"Step {step}/{MAX_STEPS} | state={self.state.name}")

            # Convergence pressure
            sys = system_prompt
            if step >= MAX_STEPS:
                sys = system_prompt + "\n\n" + self._force_prompt
                self.state = State.ANSWERING
            elif step >= SOFT_CONVERGENCE_AT:
                sys = system_prompt + "\n\n" + self._nudge_prompt.format(step=step)

            # Escalate to Pro if looping too long
            if decision and step >= 4 and decision.model == "flash":
                decision = self.router.escalate(decision, reason=f"step {step}")
                use_pro  = True

            # ── Call Gemini via Interactions API (streaming) ──────────────────
            accumulated = ""
            new_interaction_id: Optional[str] = None

            try:
                gen = self.gemini.interact_stream(
                    prompt=current_input,
                    system_instruction=sys,
                    previous_interaction_id=interaction_id,
                    use_pro=use_pro,
                    temperature=0.7,
                    max_output_tokens=4096,
                )
                for token in gen:
                    accumulated += token
                    if stream_callback:
                        stream_callback(token)

                # Retrieve interaction_id from generator return value
                try:
                    new_interaction_id = gen.send(None)
                except StopIteration as si:
                    new_interaction_id = si.value
                except Exception:
                    pass

            except Exception as e:
                logger.error(f"Gemini API error at step {step}: {e}")
                return f"[Copartner encountered an error: {e}]"

            # Update interaction thread ID
            if new_interaction_id:
                interaction_id = new_interaction_id

            # Record token usage (approximate)
            if self.budget:
                est = max(len(accumulated.split()), 100)
                self.budget.record_usage(
                    est, model="pro" if use_pro else "flash", task=query[:60]
                )

            # ── Check for final_answer ────────────────────────────────────────
            final = self.tools.has_final_answer(accumulated)
            if final:
                final_answer = final
                self.state   = State.ANSWERING
                trace.append({"tag": "final_answer", "content": final})
                # Still process any other tool tags before the final answer
                _, actions = self.tools.process_text(accumulated)
                trace.extend(a for a in actions if a.get("tag") != "final_answer")
                break

            # ── Execute tool tags, inject result as next input ────────────────
            _, actions = self.tools.process_text(accumulated)
            trace.extend(actions)

            if actions:
                self.state   = State.ACTING
                # Build result context for the next turn
                results_text = "\n".join(
                    f"[{a['tag']} result]: {a.get('result_preview', '')}"
                    for a in actions if a.get("result_preview")
                )
                current_input = (
                    f"Tool execution results:\n{results_text}\n\n"
                    "Continue reasoning based on these results. "
                    "End with <final_answer> when ready."
                )
            else:
                self.state    = State.REFLECTING
                current_input = (
                    "Continue your reasoning. "
                    "End with <final_answer>your complete response</final_answer>."
                )

        # ── Hit MAX_STEPS without final_answer ────────────────────────────────
        if not final_answer:
            logger.warning(f"Hit MAX_STEPS ({MAX_STEPS}) without <final_answer>")
            # Extract useful text from last accumulated response
            clean = re.sub(r"<[^>]+>", "", accumulated).strip()
            final_answer = clean or "I ran out of reasoning steps. Please try rephrasing."

        # ── Post-loop: save skill if task was complex ─────────────────────────
        tool_calls = sum(
            1 for t in trace if t.get("tag") not in ("think", "final_answer")
        )
        if tool_calls >= 3 and self.learner:
            self.learner.save_skill(query, trace)

        # Save to episodic memory
        if self.memory:
            self.memory.store_conversation(query, final_answer, quality=0.6)

        self.state = State.IDLE
        logger.info(f"Loop complete in {step} step(s)")
        return final_answer

    # ── Stream helper ─────────────────────────────────────────────────────────

    def stream_run(self, query: str) -> Generator[str, None, None]:
        """Generator version: yields tokens while running the loop."""
        tokens: list[str] = []

        def collect(t: str):
            tokens.append(t)

        answer = self.run(query, stream_callback=collect)
        yield from tokens
        if answer and answer not in "".join(tokens):
            yield "\n\n" + answer
