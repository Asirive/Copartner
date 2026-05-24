"""
Voice Interface for Asirive Copartner — Live API
==================================================
Real-time bidirectional voice interaction powered by the Gemini Live API.
Model: gemini-3.1-flash-live-preview (low-latency, native audio, 128k ctx)

Copartner can now LISTEN and SPEAK — not just chat.

Audio formats (from gemini-live-api-dev skill):
  Input:  Raw PCM, little-endian, 16-bit, mono, 16kHz
  Output: Raw PCM, little-endian, 16-bit, mono, 24kHz

Usage modes:
  1. PTT (Push-to-Talk):  Record → send → receive spoken answer
  2. Continuous:          Open mic stream → bidirectional conversation

Setup:
  pip install sounddevice soundfile  (for audio I/O)

Quick start:
  async with VoiceInterface.create() as voice:
      await voice.say("Hello! How can I help you today?")
      user_speech = await voice.listen_once()
      response    = await voice.ask(user_speech)
      print(response.transcript)
"""

import asyncio
import logging
import os
from typing import AsyncGenerator, Optional

logger = logging.getLogger("Copartner.VoiceInterface")

# Audio I/O — optional, gracefully disabled if not installed
try:
    import sounddevice as sd
    import numpy as np
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    logger.warning("sounddevice not installed. Audio I/O disabled. Run: pip install sounddevice numpy")

from google import genai
from google.genai import types as genai_types


# Live API constants (from skill)
LIVE_MODEL      = "gemini-3.1-flash-live-preview"
INPUT_RATE      = 16000   # Hz — Gemini Live input
OUTPUT_RATE     = 24000   # Hz — Gemini Live output
SAMPLE_WIDTH    = 2       # bytes (16-bit)
CHANNELS        = 1       # mono


class VoiceResponse:
    """Holds the result of a Live API exchange."""
    def __init__(self, transcript: str = "", audio_data: bytes = b""):
        self.transcript  = transcript    # text transcript of Gemini's response
        self.audio_data  = audio_data    # raw PCM bytes (play with sounddevice)
        self.was_interrupted = False


class VoiceInterface:
    """
    Real-time voice interface for Asirive Copartner using the Gemini Live API.

    The Live API uses WebSockets for bidirectional streaming — both audio
    and text can flow simultaneously. VAD (Voice Activity Detection) is
    built in, so interruptions are handled automatically.

    Usage (async):
        async with VoiceInterface(api_key="...") as voice:
            response = await voice.ask_text("What's the weather like?")
            print(response.transcript)
    """

    def __init__(self, api_key: Optional[str] = None, system_instruction: str = ""):
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY not set.")
        self.client = genai.Client(api_key=key)
        self.system_instruction = system_instruction or (
            "You are Copartner, an ambient AI partner built by Asirive. "
            "You are speaking directly to the user. Be concise, helpful, and brilliant. "
            "Speak naturally — no markdown, no lists unless asked."
        )
        self._session = None
        logger.info(f"VoiceInterface ready | model={LIVE_MODEL}")

    async def __aenter__(self):
        await self._connect()
        return self

    async def __aexit__(self, *args):
        await self._disconnect()

    # ── Connection ────────────────────────────────────────────────────────────

    async def _connect(self):
        """Open a Live API WebSocket session."""
        config = genai_types.LiveConnectConfig(
            response_modalities=[genai_types.Modality.AUDIO],
            system_instruction=genai_types.Content(
                parts=[genai_types.Part(text=self.system_instruction)]
            ),
            # Enable transcripts for both input and output
            input_audio_transcription=genai_types.AudioTranscriptionConfig(),
            output_audio_transcription=genai_types.AudioTranscriptionConfig(),
        )
        self._session_ctx = self.client.aio.live.connect(
            model=LIVE_MODEL,
            config=config,
        )
        self._session = await self._session_ctx.__aenter__()
        logger.info("Live API session connected")

    async def _disconnect(self):
        """Close the Live API session."""
        if self._session_ctx:
            try:
                await self._session_ctx.__aexit__(None, None, None)
            except Exception:
                pass
        self._session = None
        logger.info("Live API session closed")

    # ── Text interaction (no mic needed) ─────────────────────────────────────

    async def ask_text(self, text: str) -> VoiceResponse:
        """
        Send text to the Live API, receive audio + transcript back.
        Useful for testing without a microphone.

        Per the skill: use send_realtime_input (not send_client_content)
        for all real-time input during a session.
        """
        if not self._session:
            await self._connect()

        # Send text as realtime input
        await self._session.send_realtime_input(text=text)

        return await self._collect_response()

    # ── Audio interaction ─────────────────────────────────────────────────────

    async def ask_audio(self, audio_bytes: bytes) -> VoiceResponse:
        """
        Send raw PCM audio to the Live API.
        audio_bytes: 16-bit, mono, 16kHz PCM bytes.
        """
        if not self._session:
            await self._connect()

        await self._session.send_realtime_input(
            audio=genai_types.Blob(
                data=audio_bytes,
                mime_type="audio/pcm;rate=16000",
            )
        )
        # Signal end of audio stream
        await self._session.send_realtime_input(audio_stream_end=True)

        return await self._collect_response()

    # ── Microphone recording helper ───────────────────────────────────────────

    def record_audio(self, duration_sec: float = 5.0) -> bytes:
        """
        Record from the system microphone using sounddevice.
        Returns raw PCM bytes at 16kHz mono 16-bit.

        Args:
            duration_sec: How many seconds to record.

        Returns:
            Raw PCM bytes ready to send to ask_audio().
        """
        if not AUDIO_AVAILABLE:
            raise RuntimeError(
                "sounddevice not installed. Run: pip install sounddevice numpy"
            )
        logger.info(f"Recording {duration_sec}s from microphone...")
        audio_np = sd.rec(
            int(duration_sec * INPUT_RATE),
            samplerate=INPUT_RATE,
            channels=CHANNELS,
            dtype="int16",
        )
        sd.wait()
        return audio_np.tobytes()

    def play_audio(self, audio_bytes: bytes):
        """
        Play raw PCM audio bytes through the system speakers.
        audio_bytes: 16-bit, mono, 24kHz PCM bytes (Gemini Live output format).
        """
        if not AUDIO_AVAILABLE:
            logger.warning("sounddevice not available — cannot play audio")
            return
        if not audio_bytes:
            return
        audio_np = np.frombuffer(audio_bytes, dtype=np.int16)
        sd.play(audio_np, samplerate=OUTPUT_RATE)
        sd.wait()

    # ── Response collection ───────────────────────────────────────────────────

    async def _collect_response(self) -> VoiceResponse:
        """
        Consume Live API events until the model turn is complete.
        Collects both audio data and transcripts.

        Per the skill: a single server event can contain MULTIPLE content
        parts simultaneously — always process ALL parts in each event.
        """
        audio_chunks: list[bytes] = []
        transcript_parts: list[str] = []

        async for response in self._session.receive():
            content = response.server_content
            if not content:
                continue

            # Process ALL parts (audio chunks + text)
            if content.model_turn:
                for part in content.model_turn.parts:
                    if part.inline_data:
                        audio_chunks.append(part.inline_data.data)

            # Transcription
            if content.output_transcription:
                transcript_parts.append(content.output_transcription.text)

            # Turn complete — stop collecting
            if getattr(content, "turn_complete", False):
                break

            # Interruption — stop and clear
            if getattr(content, "interrupted", False):
                result = VoiceResponse(
                    transcript="[Interrupted]",
                    audio_data=b"".join(audio_chunks),
                )
                result.was_interrupted = True
                return result

        return VoiceResponse(
            transcript=" ".join(transcript_parts).strip(),
            audio_data=b"".join(audio_chunks),
        )

    # ── Push-to-Talk helper ───────────────────────────────────────────────────

    async def push_to_talk(self, duration_sec: float = 5.0) -> VoiceResponse:
        """
        Record audio for duration_sec, send to Live API, play the response.
        Full PTT cycle in one call.

        Returns the VoiceResponse (transcript + audio).
        """
        audio_in = self.record_audio(duration_sec)
        response = await self.ask_audio(audio_in)
        if response.audio_data:
            self.play_audio(response.audio_data)
        return response

    # ── Continuous conversation ───────────────────────────────────────────────

    async def conversation_loop(self, on_transcript=None):
        """
        Run a continuous mic → Gemini → speaker loop.
        Records 4-second chunks, sends each, plays response.
        Stops on KeyboardInterrupt.

        Args:
            on_transcript: Optional callable(user_text, gemini_text) for logging.
        """
        logger.info("Starting continuous voice conversation loop. Ctrl+C to stop.")
        print("\n🎙️  Copartner is listening... (Ctrl+C to stop)\n")

        async with self:
            while True:
                try:
                    response = await self.push_to_talk(duration_sec=4.0)
                    print(f"  Copartner: {response.transcript}")
                    if on_transcript:
                        on_transcript("", response.transcript)
                except KeyboardInterrupt:
                    print("\nEnding voice session.")
                    break
                except Exception as e:
                    logger.error(f"Voice loop error: {e}")
                    break


# ── Module-level convenience runner ──────────────────────────────────────────

async def _text_demo(api_key: str):
    """Quick demo: send a text message via Live API and print the transcript."""
    async with VoiceInterface(api_key=api_key) as voice:
        print("Asking Copartner: 'Hello, introduce yourself briefly.'")
        resp = await voice.ask_text("Hello, introduce yourself briefly.")
        print(f"\nCopartner says: {resp.transcript}")
        if resp.audio_data:
            print(f"(Audio: {len(resp.audio_data)} bytes received)")


if __name__ == "__main__":
    import sys
    key = os.environ.get("GEMINI_API_KEY") or (sys.argv[1] if len(sys.argv) > 1 else None)
    if not key:
        print("Usage: python voice_interface.py <GEMINI_API_KEY>")
        sys.exit(1)
    asyncio.run(_text_demo(key))
