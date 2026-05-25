"""
Proactive Engine for Asirive Copartner
========================================
The heart of the ambient experience. Takes observations from ScreenObserver
and IDEWatcher, classifies user intent, generates contextually relevant
suggestions, and pushes them to the UI when confidence is high enough.

Design philosophy: Copartner is a colleague, not a pest.
- Only suggests when confidence >= 0.70
- Never suggests the same thing twice in a session
- User can dismiss with "Never suggest this" → adds to blocklist
- Suggestions are actionable: one click to execute

Modes:
    PASSIVE   — observe only, never suggest (logging mode)
    ADVISORY  — observe + suggest, user approves (default, recommended)
    ACTIVE    — observe + act autonomously (not implemented, needs safety)
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Optional
from collections import deque

logger = logging.getLogger("Copartner.ProactiveEngine")

PROJECT_ROOT = Path(__file__).parent.parent
BLOCKLIST_FILE = PROJECT_ROOT / "data" / "proactive_blocklist.json"
SUGGESTION_HISTORY_FILE = PROJECT_ROOT / "data" / "suggestion_history.jsonl"


@dataclass
class Observation:
    """A single observation from the perception layer."""
    source: str           # "screen" | "ide" | "terminal" | "clipboard"
    event_type: str       # "change" | "focus" | "create" | "modify" | "delete" | "error"
    content: str          # description of what happened
    timestamp: float
    metadata: dict        # extra context (file path, app name, etc.)


@dataclass
class Suggestion:
    """A generated proactive suggestion."""
    id: str
    text: str             # what to show the user
    action: str           # what Copartner would do if accepted
    confidence: float     # 0.0 - 1.0
    source_observation: str
    timestamp: float
    dismissed: bool = False


class ProactiveEngine:
    """
    Converts raw observations into intelligent proactive suggestions.

    Pipeline:
        Observation → Pattern Detection → Intent Classification →
        Suggestion Generation → Confidence Scoring → UI Push (if >= 0.70)

    Usage:
        engine = ProactiveEngine(gemini_client=client, mode="advisory")
        engine.start()
        engine.observe(Observation(source="ide", event_type="create", content="Header.tsx", ...))
        # Suggestions pushed to UI automatically via callback
    """

    # Suggestion templates keyed by detected pattern
    # These are fast-path heuristics — no API call needed for common cases
    HEURISTIC_PATTERNS = [
        # (pattern_name, match_fn, suggestion_text, action, min_confidence)
        (
            "component_no_test",
            lambda obs: obs.source == "ide" and obs.event_type == "create"
                        and any(ext in obs.content for ext in [".tsx", ".jsx", ".vue", ".svelte"])
                        and "test" not in obs.content.lower()
                        and "spec" not in obs.content.lower(),
            "I noticed you created {file}. Want me to generate the test file?",
            "scaffold_test_for_component",
            0.75,
        ),
        (
            "multiple_components_no_index",
            lambda obs, ctx: ctx.get("recent_creations", 0) >= 3
                             and not ctx.get("has_index", False)
                             and obs.source == "ide",
            "You've created {count} components in this folder. Want me to generate an index.ts barrel file?",
            "generate_barrel_file",
            0.72,
        ),
        (
            "new_project_no_readme",
            lambda obs, ctx: ctx.get("is_new_project", False)
                             and not ctx.get("has_readme", False)
                             and obs.source == "ide",
            "This looks like a new project. Want me to generate a README.md?",
            "generate_readme",
            0.70,
        ),
        (
            "screen_error_visible",
            lambda obs: obs.source == "screen"
                        and obs.event_type == "error"
                        and any(kw in obs.content.lower() for kw in ["error", "exception", "failed", "traceback"]),
            "I see an error on your screen: {error_summary}. Want me to help debug it?",
            "debug_screen_error",
            0.80,
        ),
        (
            "long_inactive_screen",
            lambda obs: obs.source == "screen"
                        and obs.event_type == "inactive"
                        and obs.metadata.get("inactive_sec", 0) > 300,
            "You've been on this screen for 5 minutes. Stuck on something?",
            "ask_if_stuck",
            0.65,  # Below threshold — will need Gemini boost
        ),
        (
            "package_json_no_lock",
            lambda obs, ctx: "package.json" in obs.content
                             and not ctx.get("has_lockfile", False)
                             and obs.source == "ide",
            "I see a package.json but no lockfile. Want me to run `npm install`?",
            "run_package_install",
            0.70,
        ),
    ]

    def __init__(
        self,
        gemini_client=None,
        mode: str = "advisory",
        confidence_threshold: float = 0.70,
        cooldown_sec: float = 30.0,
        on_suggestion: Optional[Callable[[Suggestion], None]] = None,
    ):
        self.gemini = gemini_client
        self.mode = mode
        self.threshold = confidence_threshold
        self.cooldown = cooldown_sec
        self.on_suggestion = on_suggestion

        # State
        self._context: dict = {}          # accumulated context from observations
        self._recent_obs: deque = deque(maxlen=50)
        self._suggested_this_session: set = set()
        self._blocklist: set = self._load_blocklist()
        self._last_suggestion_time: float = 0.0
        self._running = False
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        """Start the observation processing loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info(f"ProactiveEngine started [{self.mode} mode, threshold={self.threshold}]")

    def stop(self):
        """Stop the processing loop."""
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("ProactiveEngine stopped")

    # ── Observation intake ────────────────────────────────────────────────────

    def observe(self, observation: Observation):
        """Called by ScreenObserver, IDEWatcher, etc. when something happens."""
        if not self._running or self.mode == "passive":
            return

        self._recent_obs.append(observation)
        self._update_context(observation)

        # Fast-path heuristics (no API call)
        suggestion = self._check_heuristics(observation)
        if suggestion and suggestion.confidence >= self.threshold:
            self._maybe_emit(suggestion)
            return

        # If heuristic matched but confidence is borderline, ask Gemini to boost
        if suggestion and self.gemini:
            asyncio.create_task(self._boost_with_gemini(suggestion, observation))

    def _update_context(self, obs: Observation):
        """Update accumulated context from observations."""
        # Track recent file creations
        if obs.source == "ide" and obs.event_type == "create":
            self._context["recent_creations"] = self._context.get("recent_creations", 0) + 1
            path = obs.metadata.get("path", "")
            if "index" in path.lower() or "barrel" in path.lower():
                self._context["has_index"] = True
            if "readme" in path.lower():
                self._context["has_readme"] = True
            if "package.json" in path.lower():
                self._context["has_package_json"] = True
            if any(lock in path for lock in ["package-lock", "yarn.lock", "pnpm-lock"]):
                self._context["has_lockfile"] = True

        # Track if this looks like a new project
        if self._context.get("recent_creations", 0) >= 2 and self._context.get("has_package_json"):
            self._context["is_new_project"] = True

        # Track screen errors
        if obs.source == "screen" and "error" in obs.content.lower():
            self._context["last_screen_error"] = obs.content[:200]

    # ── Heuristic matching ────────────────────────────────────────────────────

    def _check_heuristics(self, obs: Observation) -> Optional[Suggestion]:
        """Check observation against fast heuristic patterns."""
        for pattern_name, matcher, template, action, confidence in self.HEURISTIC_PATTERNS:
            try:
                sig = matcher.__code__.co_argcount
                matched = matcher(obs, self._context) if sig >= 2 else matcher(obs)
            except Exception:
                continue

            if matched:
                text = template.format(
                    file=obs.metadata.get("path", obs.content),
                    count=self._context.get("recent_creations", 0),
                    error_summary=self._context.get("last_screen_error", "an error")[:80],
                )
                return Suggestion(
                    id=f"{pattern_name}_{int(time.time())}",
                    text=text,
                    action=action,
                    confidence=confidence,
                    source_observation=obs.content,
                    timestamp=time.time(),
                )
        return None

    # ── Gemini confidence boost ───────────────────────────────────────────────

    async def _boost_with_gemini(self, suggestion: Suggestion, obs: Observation):
        """Ask Gemini Flash if this suggestion is actually relevant right now."""
        if not self.gemini:
            return

        prompt = (
            f"User observation: {obs.content}\n"
            f"Suggested action: {suggestion.text}\n"
            f"Context: {json.dumps(self._context, default=str)}\n\n"
            "Rate how relevant this suggestion is RIGHT NOW for this user. "
            "Respond with ONLY a number from 0.0 to 1.0. Nothing else."
        )
        try:
            # Use Flash for speed (cheap, fast)
            from google.genai import types as genai_types
            resp = self.gemini.client.models.generate_content(
                model=self.gemini.models["flash"],
                contents=[genai_types.Part.from_text(text=prompt)],
                config=genai_types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=10,
                ),
            )
            score_text = resp.text.strip() if resp.text else "0"
            score = float("".join(c for c in score_text if c.isdigit() or c == "."))
            score = max(0.0, min(1.0, score))

            if score >= self.threshold:
                suggestion.confidence = score
                self._maybe_emit(suggestion)
        except Exception as e:
            logger.debug(f"Gemini boost failed: {e}")

    # ── Emission logic ────────────────────────────────────────────────────────

    def _maybe_emit(self, suggestion: Suggestion):
        """Emit suggestion if it passes all filters."""
        # Cooldown
        now = time.time()
        if now - self._last_suggestion_time < self.cooldown:
            return

        # Deduplication
        dedup_key = suggestion.action + ":" + suggestion.source_observation[:60]
        if dedup_key in self._suggested_this_session:
            return

        # Blocklist
        if suggestion.action in self._blocklist:
            return

        self._suggested_this_session.add(dedup_key)
        self._last_suggestion_time = now

        logger.info(f"Proactive suggestion [{suggestion.confidence:.2f}]: {suggestion.text[:80]}")

        # Persist to history
        self._log_suggestion(suggestion)

        # Push to UI
        if self.on_suggestion:
            try:
                self.on_suggestion(suggestion)
            except Exception as e:
                logger.error(f"on_suggestion callback failed: {e}")

    # ── User feedback ─────────────────────────────────────────────────────────

    def dismiss(self, suggestion_id: str, never_again: bool = False):
        """Called when user dismisses a suggestion."""
        if never_again:
            # Find the action type and block it
            # (In practice the UI sends back the action name)
            pass

    def block_action(self, action: str):
        """Permanently block a type of suggestion."""
        self._blocklist.add(action)
        self._save_blocklist()
        logger.info(f"Action blocked: {action}")

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_blocklist(self) -> set:
        if BLOCKLIST_FILE.exists():
            try:
                return set(json.loads(BLOCKLIST_FILE.read_text()))
            except Exception:
                pass
        return set()

    def _save_blocklist(self):
        BLOCKLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        BLOCKLIST_FILE.write_text(json.dumps(list(self._blocklist)))

    def _log_suggestion(self, suggestion: Suggestion):
        SUGGESTION_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": suggestion.timestamp,
            "text": suggestion.text,
            "action": suggestion.action,
            "confidence": suggestion.confidence,
            "source": suggestion.source_observation,
        }
        with open(SUGGESTION_HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    # ── Background loop (for async processing) ────────────────────────────────

    async def _process_loop(self):
        """Optional background loop for batch processing."""
        while self._running:
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break

    def get_stats(self) -> dict:
        """Return engine statistics."""
        return {
            "mode": self.mode,
            "observations_this_session": len(self._recent_obs),
            "suggestions_this_session": len(self._suggested_this_session),
            "blocked_actions": len(self._blocklist),
            "context_keys": list(self._context.keys()),
        }
