"""
Gemini Client for Asirive Copartner
======================================
The primary brain interface — wraps the google-genai SDK (>= 2.0.0).

Uses the INTERACTIONS API (client.interactions.create) as the primary
interface for all generation tasks. Key advantages over the old
generate_content() approach:
  - Stateful conversation via previous_interaction_id (server manages context)
  - Built-in streaming with structured step events
  - Native tool use, code execution, and Google Search grounding
  - Deep Research agent access

Current models (from gemini-api-dev skill — overrides any training knowledge):
  - gemini-3.5-flash       : fast, multimodal, 1M ctx — default for most tasks
  - gemini-3.1-pro-preview : complex reasoning, coding, research — deep tasks
  - gemini-3.1-flash-lite-preview : cost-efficient, highest frequency tasks
  - gemini-3.1-flash-live-preview : real-time voice (Live API)

DEPRECATED (never use):
  - gemini-2.5-*, gemini-2.0-*, gemini-1.5-*  ← all legacy, do not use
"""

import logging
import os
from typing import Generator, Optional

from google import genai

logger = logging.getLogger("Copartner.GeminiClient")


class GeminiClient:
    """
    Primary brain interface for Asirive Copartner.

    Uses the Interactions API for stateful conversation and streaming.
    Falls back to models.generate_content() only for embeddings and
    multimodal (image) calls where the Interactions API isn't needed.
    """

    # Current model identifiers (from gemini-api-dev + gemini-interactions-api skills)
    MODELS = {
        "flash":      "gemini-3.5-flash",            # fast, multimodal, default
        "pro":        "gemini-3.1-pro-preview",       # deep reasoning, coding
        "lite":       "gemini-3.1-flash-lite-preview", # high-frequency, cheapest
        "live":       "gemini-3.1-flash-live-preview", # real-time voice (Live API)
        "embedding":  "gemini-embedding-2",            # ChromaDB embeddings
    }

    def __init__(self, api_key: Optional[str] = None):
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ValueError(
                "GEMINI_API_KEY not set. Add it to your .env file."
            )
        self.client = genai.Client(api_key=key)
        # expose for backwards compatibility (screen_observer, etc.)
        self.models = self.MODELS
        logger.info(
            f"GeminiClient ready | flash={self.MODELS['flash']} "
            f"pro={self.MODELS['pro']}"
        )

    # ── Primary: Interactions API ─────────────────────────────────────────────

    def interact(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        previous_interaction_id: Optional[str] = None,
        use_pro: bool = False,
        temperature: float = 0.7,
        max_output_tokens: int = 8192,
        tools: Optional[list] = None,
    ) -> tuple[str, str]:
        """
        Single-turn interaction using the Interactions API.

        Stateful: pass previous_interaction_id to continue a conversation.
        The server manages context — no need to track message history manually.

        Args:
            prompt:                   User input text.
            system_instruction:       Optional system prompt.
            previous_interaction_id:  ID from a prior interaction to continue the thread.
            use_pro:                  True = gemini-3.1-pro-preview, False = gemini-3.5-flash.
            temperature:              Sampling temperature.
            max_output_tokens:        Max tokens in the response.
            tools:                    Optional list of Gemini tool configs.

        Returns:
            (response_text, interaction_id)
            interaction_id can be passed as previous_interaction_id next turn.
        """
        model = self.MODELS["pro"] if use_pro else self.MODELS["flash"]

        kwargs: dict = {
            "model": model,
            "input": prompt,
            "generation_config": {
                "temperature": temperature,
                "max_output_tokens": max_output_tokens,
            },
        }
        if system_instruction:
            kwargs["system_instruction"] = system_instruction
        if previous_interaction_id:
            kwargs["previous_interaction_id"] = previous_interaction_id
        if tools:
            kwargs["tools"] = tools

        try:
            interaction = self.client.interactions.create(**kwargs)
            text = interaction.steps[-1].content[0].text if interaction.steps else ""
            logger.debug(f"interact() → {len(text)} chars | id={interaction.id}")
            return text, interaction.id
        except Exception as e:
            logger.error(f"interact() failed [{model}]: {e}")
            raise

    def interact_stream(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        previous_interaction_id: Optional[str] = None,
        use_pro: bool = False,
        temperature: float = 0.7,
        max_output_tokens: int = 8192,
    ) -> Generator[str, None, str]:
        """
        Streaming interaction using the Interactions API.

        Yields text tokens in real time. Returns the interaction_id on completion
        (accessible via generator.send() or StopIteration.value).

        Usage:
            gen = client.interact_stream("Tell me a story")
            for token in gen:
                print(token, end="", flush=True)
        """
        model = self.MODELS["pro"] if use_pro else self.MODELS["flash"]

        kwargs: dict = {
            "model": model,
            "input": prompt,
            "stream": True,
            "generation_config": {
                "temperature": temperature,
                "max_output_tokens": max_output_tokens,
            },
        }
        if system_instruction:
            kwargs["system_instruction"] = system_instruction
        if previous_interaction_id:
            kwargs["previous_interaction_id"] = previous_interaction_id

        interaction_id = None
        token_count    = 0

        try:
            for event in self.client.interactions.create(**kwargs):
                # Text token delta
                if event.event_type == "step.delta":
                    if event.delta.type == "text":
                        yield event.delta.text
                        token_count += 1
                    elif event.delta.type == "thought_summary":
                        # Thinking traces — yield with a visual marker
                        text = (
                            getattr(event.delta, "text", None)
                            or (event.delta.content or {}).get("text", "")
                        )
                        if text:
                            yield f"[thinking] {text}"

                # Capture interaction ID when complete
                elif event.event_type == "interaction.complete":
                    interaction_id = getattr(event.interaction, "id", None)
                    usage = getattr(event.interaction, "usage", None)
                    if usage:
                        logger.debug(
                            f"interact_stream() complete | "
                            f"tokens={usage.total_tokens} | id={interaction_id}"
                        )

            return interaction_id  # StopIteration.value

        except Exception as e:
            logger.error(f"interact_stream() failed [{model}]: {e}")
            raise

    def generate(
        self,
        contents,
        use_pro: bool = True,
        temperature: float = 0.3,
        max_output_tokens: int = 8192,
        system_instruction: Optional[str] = None,
    ) -> str:
        """
        Synchronous generate_content() call using the models API.
        Used for: multimodal (image + text), embeddings context,
        scaffold prompts that return raw JSON.

        For standard text conversation prefer interact() instead.
        """
        from google.genai import types

        model = self.MODELS["pro"] if use_pro else self.MODELS["flash"]

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            system_instruction=system_instruction,
        )
        try:
            resp = self.client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            return resp.text or ""
        except Exception as e:
            logger.error(f"generate() failed [{model}]: {e}")
            raise

    def generate_stream(
        self,
        contents,
        use_pro: bool = False,
        temperature: float = 0.7,
        max_output_tokens: int = 4096,
        system_instruction: Optional[str] = None,
        **_kwargs,  # absorb legacy keyword args from ThoughtController
    ) -> Generator[str, None, None]:
        """
        Streaming generate_content_stream() call using the models API.
        Kept for backwards compatibility with ThoughtController and ScreenObserver.
        New code should prefer interact_stream() which is stateful.
        """
        from google.genai import types

        model = self.MODELS["pro"] if use_pro else self.MODELS["flash"]
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            system_instruction=system_instruction,
        )
        try:
            for chunk in self.client.models.generate_content_stream(
                model=model,
                contents=contents,
                config=config,
            ):
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logger.error(f"generate_stream() failed [{model}]: {e}")
            raise

    # ── Embeddings ────────────────────────────────────────────────────────────

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """
        Generate text embeddings using text-embedding-004.
        Used by GeminiEmbedder → ChromaDB memory system.
        """
        if isinstance(texts, str):
            texts = [texts]
        try:
            resp = self.client.models.embed_content(
                model=self.MODELS["embedding"],
                contents=texts,
                config={"output_dimensionality": 768},
            )
            return [emb.values for emb in resp.embeddings]
        except Exception as e:
            logger.error(f"get_embeddings() failed: {e}")
            raise

    # ── Deep Research ─────────────────────────────────────────────────────────

    def deep_research(self, query: str, exhaustive: bool = False) -> str:
        """
        Run a Deep Research task via the Interactions API.
        Runs in background and polls until complete.

        Args:
            query:     The research question.
            exhaustive: True = deep-research-max (slower, thorough).

        Returns:
            The research report as a string.
        """
        import time
        agent = (
            "deep-research-max-preview-04-2026"
            if exhaustive
            else "deep-research-preview-04-2026"
        )
        logger.info(f"Starting Deep Research: {query[:60]}")
        try:
            interaction = self.client.interactions.create(
                agent=agent,
                input=query,
                background=True,
            )
            # Poll for completion
            for _ in range(60):  # max 10 min wait (60 × 10s)
                interaction = self.client.interactions.get(interaction.id)
                if interaction.status == "completed":
                    return interaction.steps[-1].content[0].text
                elif interaction.status in ("failed", "cancelled"):
                    return f"[Deep Research failed: {interaction.status}]"
                time.sleep(10)
            return "[Deep Research timed out after 10 minutes]"
        except Exception as e:
            logger.error(f"deep_research() failed: {e}")
            return f"[Deep Research error: {e}]"

    # ── Token counting ────────────────────────────────────────────────────────

    def count_tokens(self, contents, use_pro: bool = False) -> int:
        """Count input tokens. Used by TokenBudget for pre-call estimation."""
        model = self.MODELS["pro"] if use_pro else self.MODELS["flash"]
        try:
            resp = self.client.models.count_tokens(model=model, contents=contents)
            return resp.total_tokens
        except Exception as e:
            logger.warning(f"count_tokens() failed: {e}")
            return 0
