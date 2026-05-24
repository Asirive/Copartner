"""
Screen Observer for Asirive Copartner — Phase 2 Perception
============================================================
Captures screenshots using mss, detects significant screen changes via
pixel diff, and sends frames to Gemini (multimodal) for understanding.

The Gemini models (2.5 Pro & Flash) are natively multimodal — images are
passed directly in the API contents list alongside text. No separate
"vision model" exists; it's the same Flash/Pro you're already using.

Modes:
    PASSIVE  — capture + log, never act (background monitoring)
    ADVISORY — capture + analyse + suggest (notification only)
    ACTIVE   — capture + analyse + trigger ThoughtController actions

Trigger types:
    - App focus change detected (window title diff)
    - Significant pixel change (>15% of screen differs)
    - Manual trigger via ThoughtController <observe_screen> tag
"""

import io
import logging
import time
import threading
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("Copartner.ScreenObserver")

try:
    import mss
    import mss.tools
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False
    logger.warning("mss not installed. Run: pip install mss")

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class ObserverMode(Enum):
    PASSIVE  = "passive"
    ADVISORY = "advisory"
    ACTIVE   = "active"


def _compute_diff_ratio(img1_bytes: bytes, img2_bytes: bytes) -> float:
    """
    Compute rough pixel difference ratio between two PNG screenshots.
    Returns 0.0 (identical) to 1.0 (completely different).
    Uses downsampled comparison for speed.
    """
    if not PIL_AVAILABLE:
        return 1.0  # Assume change if PIL unavailable

    try:
        img1 = Image.open(io.BytesIO(img1_bytes)).convert("RGB").resize((160, 90))
        img2 = Image.open(io.BytesIO(img2_bytes)).convert("RGB").resize((160, 90))

        px1 = list(img1.getdata())
        px2 = list(img2.getdata())

        diffs = sum(
            1 for (r1, g1, b1), (r2, g2, b2) in zip(px1, px2)
            if abs(r1 - r2) + abs(g1 - g2) + abs(b1 - b2) > 30
        )
        return diffs / len(px1)
    except Exception:
        return 1.0


class ScreenObserver:
    """
    Ambient screen observer that feeds Gemini multimodal context.

    Usage:
        observer = ScreenObserver(gemini_client=client, mode=ObserverMode.ADVISORY)
        observer.start()                              # background thread
        context = observer.capture_and_analyze("What is the user doing?")  # one-shot
    """

    def __init__(
        self,
        gemini_client=None,
        mode: ObserverMode = ObserverMode.PASSIVE,
        capture_interval_sec: float = 5.0,
        diff_threshold: float = 0.15,
        on_change: Optional[Callable[[str], None]] = None,
    ):
        self.gemini           = gemini_client
        self.mode             = mode
        self.interval         = capture_interval_sec
        self.diff_threshold   = diff_threshold
        self.on_change        = on_change  # callback(analysis_text)

        self._last_frame: Optional[bytes] = None
        self._running       = False
        self._thread: Optional[threading.Thread] = None
        self._last_analysis = ""

        if not MSS_AVAILABLE:
            logger.error("mss is required for ScreenObserver. Install: pip install mss")

    # ── Screenshot capture ────────────────────────────────────────────────────

    def capture(self) -> Optional[bytes]:
        """Capture the full primary monitor as PNG bytes."""
        if not MSS_AVAILABLE:
            return None
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]   # Primary monitor
                frame   = sct.grab(monitor)
                buf = io.BytesIO()
                mss.tools.to_png(frame.rgb, frame.size, output=buf)
                return buf.getvalue()
        except Exception as e:
            logger.error(f"Screen capture failed: {e}")
            return None

    def capture_region(self, top: int, left: int, width: int, height: int) -> Optional[bytes]:
        """Capture a specific screen region."""
        if not MSS_AVAILABLE:
            return None
        try:
            with mss.mss() as sct:
                region = {"top": top, "left": left, "width": width, "height": height}
                frame  = sct.grab(region)
                buf = io.BytesIO()
                mss.tools.to_png(frame.rgb, frame.size, output=buf)
                return buf.getvalue()
        except Exception as e:
            logger.error(f"Region capture failed: {e}")
            return None

    # ── Gemini multimodal analysis ────────────────────────────────────────────

    def analyze(self, screenshot_bytes: bytes, instruction: str = "") -> str:
        """
        Send a screenshot to Gemini (multimodal) for analysis.

        Gemini 2.5 Flash/Pro are natively multimodal — the image is passed
        directly in the contents list alongside the text prompt. No separate
        vision model or API endpoint is needed.

        Args:
            screenshot_bytes: PNG image bytes from capture().
            instruction:      Specific thing to look for (optional).

        Returns:
            Gemini's analysis as a string.
        """
        if self.gemini is None:
            return "[Screen analysis unavailable — GeminiClient not injected]"
        if screenshot_bytes is None:
            return "[No screenshot available]"

        prompt = instruction or (
            "Describe what is currently on the screen. "
            "What application is open? What is the user working on? "
            "Any errors or important information visible?"
        )

        try:
            from google.genai import types as genai_types

            # Build multimodal content: [image_part, text_part]
            # Gemini accepts inline image bytes directly
            image_part = genai_types.Part.from_bytes(
                data=screenshot_bytes,
                mime_type="image/png",
            )
            text_part = genai_types.Part.from_text(text=prompt)

            # Use Flash for speed (Vision tasks don't need Pro's deep reasoning)
            response = self.gemini.client.models.generate_content(
                model=self.gemini.models["flash"],
                contents=[image_part, text_part],
            )
            analysis = response.text or "[no analysis returned]"
            self._last_analysis = analysis
            logger.debug(f"Screen analysis: {analysis[:120]}")
            return analysis

        except Exception as e:
            logger.error(f"Gemini screen analysis failed: {e}")
            return f"[Screen analysis error: {e}]"

    def capture_and_analyze(self, instruction: str = "") -> str:
        """Convenience: capture current screen and analyze it in one call."""
        frame = self.capture()
        if frame is None:
            return "[Screen capture failed]"
        return self.analyze(frame, instruction)

    # ── Background monitoring ─────────────────────────────────────────────────

    def start(self):
        """Start background screen monitoring thread."""
        if not MSS_AVAILABLE:
            return
        if self._running:
            logger.warning("ScreenObserver already running")
            return

        self._running = True
        self._thread  = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info(f"ScreenObserver started [{self.mode.value} mode, {self.interval}s interval]")

    def stop(self):
        """Stop the background monitoring thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("ScreenObserver stopped")

    def _monitor_loop(self):
        """Background loop: capture → diff → analyse on significant change."""
        while self._running:
            frame = self.capture()

            if frame is not None and self._last_frame is not None:
                diff = _compute_diff_ratio(self._last_frame, frame)

                if diff >= self.diff_threshold:
                    logger.debug(f"Screen change detected ({diff:.1%})")

                    if self.mode in (ObserverMode.ADVISORY, ObserverMode.ACTIVE):
                        analysis = self.analyze(frame)
                        if self.on_change and analysis:
                            self.on_change(analysis)

            self._last_frame = frame
            time.sleep(self.interval)

    @property
    def last_analysis(self) -> str:
        """Return the most recent screen analysis text."""
        return self._last_analysis
