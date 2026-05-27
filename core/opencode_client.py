"""
OpenCode Go Client for Asirive Copartner
==========================================
Provides access to cheap open-source models via the OpenCode Go subscription
($10/month flat). OpenCode Go exposes an OpenAI-compatible REST API, so we
use the `openai` Python SDK pointed at their endpoint.

Available models (from opencode.ai/docs/go):
  - kimi-k2.5 / kimi-k2.6       — Moonshot AI, strong coding
  - glm-5 / glm-5.1             — Zhipu AI, multilingual
  - mimo-v2.5 / mimo-v2.5-pro   — MiMo, efficient reasoning
  - minimax-m2.5                 — MiniMax, long-context
  - qwen3-235b-a22b             — Alibaba Qwen, MoE
  - deepseek-r2-0528            — DeepSeek, reasoning
  + more via /models endpoint

Strategy (cost routing):
  - Use Gemini (Flash/Pro) for: real-time streaming, voice, multimodal, memory
  - Use OpenCode for: batch code generation, scaffolding, long-form drafting
  - This can cut API costs by 80-90% for heavy generation tasks

Base URL: https://go.opencode.ai/v1  (OpenAI-compatible)
"""

import logging
import os
from typing import Generator, Optional

logger = logging.getLogger("Copartner.OpenCodeClient")

try:
    from openai import OpenAI
    OPENAI_SDK_AVAILABLE = True
except ImportError:
    OPENAI_SDK_AVAILABLE = False
    logger.warning("openai SDK not installed. Run: pip install openai")


# Default model preferences (best quality/cost tradeoff from Go roster)
# NOTE: kimi-k2.6 emits reasoning tokens BEFORE the actual response.
# These reasoning tokens count against max_tokens, so we set max_tokens
# very high (64K) to ensure there's room for both reasoning + output.
DEFAULT_MODEL    = "kimi-k2.6"      # strongest coding model, reasoning-enabled
REASONING_MODEL  = "deepseek-v4-pro"  # deep reasoning tasks
LONG_CTX_MODEL   = "minimax-m2.5"   # long documents / context
FAST_MODEL       = "qwen3.5-plus"   # quick completions, cheapest

OPENCODE_BASE_URL = "https://opencode.ai/zen/go/v1"


class OpenCodeClient:
    """
    Client for OpenCode Go open-source models.

    Uses the OpenAI Python SDK pointed at OpenCode's compatible endpoint.
    Integrated into IntentRouter so the ThoughtController can auto-route
    heavy generation tasks here to save Gemini budget.

    Usage:
        client = OpenCodeClient()
        text = client.generate("Write a FastAPI health check endpoint")
        for token in client.stream("Explain async/await in Python"):
            print(token, end="", flush=True)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        if not OPENAI_SDK_AVAILABLE:
            logger.error("openai package required. Install: pip install openai")
            self._ready = False
            return

        key = api_key or os.environ.get("OPENCODE_API_KEY", "")
        url = base_url or os.environ.get("OPENCODE_BASE_URL", OPENCODE_BASE_URL)

        if not key:
            logger.warning(
                "OPENCODE_API_KEY not set. OpenCode client in demo mode. "
                "Set key in .env to enable open-source model routing."
            )
            self._ready = False
            return

        self._client = OpenAI(api_key=key, base_url=url)
        self._ready  = True
        logger.info(f"OpenCodeClient ready | base_url={url}")

    @property
    def ready(self) -> bool:
        return self._ready

    # ── Generation ────────────────────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 64000,
    ) -> str:
        """
        Synchronous text generation using an OpenCode Go model.

        Args:
            prompt:             User message.
            system_instruction: Optional system prompt.
            model:              Model ID. Defaults to kimi-k2.6.
            temperature:        Sampling temperature.
            max_tokens:         Max output tokens.

        Returns:
            Generated text as a string.
        """
        if not self._ready:
            return "[OpenCode unavailable — OPENCODE_API_KEY not set]"

        use_model = model or DEFAULT_MODEL
        messages  = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        try:
            resp = self._client.chat.completions.create(
                model=use_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = resp.choices[0].message.content or ""
            logger.debug(f"OpenCode [{use_model}]: {len(text)} chars generated")
            return text
        except Exception as e:
            logger.error(f"OpenCode generate() failed [{use_model}]: {e}")
            return f"[OpenCode error: {e}]"

    def stream(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.5,
        max_tokens: int = 64000,
    ) -> Generator[str, None, None]:
        """
        Streaming text generation using an OpenCode Go model.
        Yields text tokens as they arrive.
        """
        if not self._ready:
            yield "[OpenCode unavailable — OPENCODE_API_KEY not set]"
            return

        use_model = model or DEFAULT_MODEL
        messages  = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        try:
            stream = self._client.chat.completions.create(
                model=use_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content
        except Exception as e:
            logger.error(f"OpenCode stream() failed [{use_model}]: {e}")
            yield f"[OpenCode error: {e}]"

    def list_models(self) -> list[str]:
        """Fetch available models from the OpenCode Go endpoint."""
        if not self._ready:
            return []
        try:
            models = self._client.models.list()
            return [m.id for m in models.data]
        except Exception as e:
            logger.error(f"OpenCode list_models() failed: {e}")
            return []

    # ── Scaffold helper (primary use case for OpenCode) ───────────────────────

    def scaffold_with_opencode(
        self,
        brief: str,
        system_instruction: Optional[str] = None,
    ) -> str:
        """
        Use OpenCode's Kimi K2 or DeepSeek for code scaffolding tasks.
        This is ~10x cheaper than using Gemini Pro for the same task.

        Returns raw text (JSON expected — parse in CodeScaffolder).
        """
        sys = system_instruction or (
            "You are an expert software engineer. Generate complete, "
            "production-ready project scaffolds. Output strict JSON only."
        )
        return self.generate(
            prompt=brief,
            system_instruction=sys,
            model=DEFAULT_MODEL,   # kimi-k2.6 — strongest coding model
            temperature=0.2,
            max_tokens=64000,      # Very high limit: reasoning tokens + output
        )
