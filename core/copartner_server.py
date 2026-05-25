"""
Copartner WebSocket Server
==========================
Bridges the React/Tauri frontend (ws://127.0.0.1:8765) to the Python brain.

NEW: Ambient mode — starts ScreenObserver + IDEWatcher + ProactiveEngine on boot.
Copartner now watches your screen and files, then reaches out proactively.

Run as:
    python -m core.copartner_server          (preferred)
    python core/copartner_server.py          (also works — auto-bootstraps sys.path)
"""

from __future__ import annotations

import sys
import asyncio
import json
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any

# ── Bootstrap when launched directly (not via -m) ────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Load .env before importing anything that reads GEMINI_API_KEY
try:
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

from websockets.server import serve  # noqa: E402
from core.thought_controller import ThoughtController  # noqa: E402
from core.proactive_engine import ProactiveEngine, Observation  # noqa: E402
from perception.screen_observer import ScreenObserver, ObserverMode  # noqa: E402
from perception.ide_watcher import IDEWatcher  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("Copartner.Server")

# ── Default watch path — current Copartner project for now ───────────────────
DEFAULT_WATCH_PATH = _PROJECT_ROOT


class CopartnerServer:
    HOST = "127.0.0.1"
    PORT = 8765

    def __init__(self) -> None:
        logger.info("Booting ThoughtController...")
        self.thought_controller = ThoughtController.create()
        self.connected_clients: set = set()
        self._executor = ThreadPoolExecutor(max_workers=2)
        logger.info("ThoughtController ready.")

        # ── Ambient layer (started in async start()) ──────────────────────────
        self.screen_observer: ScreenObserver | None = None
        self.ide_watcher: IDEWatcher | None = None
        self.proactive_engine: ProactiveEngine | None = None

    async def _init_ambient_layer(self):
        """Start ScreenObserver, IDEWatcher, and ProactiveEngine."""
        gemini_client = self.thought_controller.gemini
        behavior_engine = self.thought_controller.behavior

        # ProactiveEngine: converts observations → suggestions
        self.proactive_engine = ProactiveEngine(
            gemini_client=gemini_client,
            mode="advisory",
            confidence_threshold=0.70,
            cooldown_sec=30.0,
            on_suggestion=self._on_proactive_suggestion,
        )
        self.proactive_engine.start()

        # ScreenObserver: captures screen, detects changes
        self.screen_observer = ScreenObserver(
            gemini_client=gemini_client,
            mode=ObserverMode.ADVISORY,
            capture_interval_sec=5.0,
            diff_threshold=0.15,
            on_change=self._on_screen_change,
        )
        self.screen_observer.start()

        # IDEWatcher: monitors file system
        self.ide_watcher = IDEWatcher(
            watch_path=DEFAULT_WATCH_PATH,
            behavioral_engine=behavior_engine,
            on_create=self._on_file_create,
            on_modify=self._on_file_modify,
            on_delete=self._on_file_delete,
        )
        self.ide_watcher.start()

        logger.info(
            f"Ambient layer active: ScreenObserver[{ObserverMode.ADVISORY.value}], "
            f"IDEWatcher[{DEFAULT_WATCH_PATH.name}]"
        )

    # ── Callbacks from perception layer ───────────────────────────────────────

    def _on_screen_change(self, analysis: str):
        """Called when ScreenObserver detects a significant screen change."""
        if self.proactive_engine:
            self.proactive_engine.observe(Observation(
                source="screen",
                event_type="change",
                content=analysis,
                timestamp=asyncio.get_event_loop().time(),
                metadata={},
            ))

    def _on_file_create(self, path: str, content: str):
        """Called when IDEWatcher detects a new file."""
        if self.proactive_engine:
            self.proactive_engine.observe(Observation(
                source="ide",
                event_type="create",
                content=Path(path).name,
                timestamp=asyncio.get_event_loop().time(),
                metadata={"path": path, "content_preview": content[:200]},
            ))

    def _on_file_modify(self, path: str, content: str):
        """Called when IDEWatcher detects a modified file."""
        if self.proactive_engine:
            self.proactive_engine.observe(Observation(
                source="ide",
                event_type="modify",
                content=Path(path).name,
                timestamp=asyncio.get_event_loop().time(),
                metadata={"path": path, "content_preview": content[:200]},
            ))

    def _on_file_delete(self, path: str):
        """Called when IDEWatcher detects a deleted file."""
        if self.proactive_engine:
            self.proactive_engine.observe(Observation(
                source="ide",
                event_type="delete",
                content=Path(path).name,
                timestamp=asyncio.get_event_loop().time(),
                metadata={"path": path},
            ))

    def _on_proactive_suggestion(self, suggestion):
        """Called when ProactiveEngine generates a high-confidence suggestion."""
        asyncio.create_task(self._broadcast_suggestion(suggestion))

    async def _broadcast_suggestion(self, suggestion):
        """Push a proactive suggestion to all connected Tauri clients."""
        if not self.connected_clients:
            return
        payload = {
            "id": suggestion.id,
            "text": suggestion.text,
            "action": suggestion.action,
            "confidence": suggestion.confidence,
        }
        message = json.dumps({"type": "proactive_suggestion", "payload": payload})
        await asyncio.gather(
            *(c.send(message) for c in self.connected_clients),
            return_exceptions=True,
        )
        logger.info(f"Broadcasted suggestion to {len(self.connected_clients)} client(s)")

    # ── WebSocket helpers ─────────────────────────────────────────────────────

    async def broadcast_state(self, state_update: Dict[str, Any]) -> None:
        if not self.connected_clients:
            return
        message = json.dumps({"type": "state_update", "payload": state_update})
        await asyncio.gather(
            *(c.send(message) for c in self.connected_clients),
            return_exceptions=True,
        )

    async def _send(self, websocket, type_: str, payload: Dict[str, Any]) -> None:
        try:
            await websocket.send(json.dumps({"type": type_, "payload": payload}))
        except Exception as e:
            logger.warning(f"send failed: {e}")

    # ── Query processing ──────────────────────────────────────────────────────

    async def _process_query(self, websocket, query_text: str) -> None:
        await self.broadcast_state({"status": "Thinking"})
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def stream_cb(token: str) -> None:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, token)
            except RuntimeError:
                pass

        def run_brain() -> str:
            return self.thought_controller.run(query_text, stream_callback=stream_cb)

        future = loop.run_in_executor(self._executor, run_brain)

        async def pump():
            while not future.done() or not queue.empty():
                try:
                    token = await asyncio.wait_for(queue.get(), timeout=0.2)
                    await self._send(websocket, "stream_chunk", {"text": token})
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.warning(f"pump error: {e}")
                    break

        pump_task = asyncio.create_task(pump())
        try:
            answer = await future
        except Exception as e:
            logger.exception("Brain error")
            await self._send(websocket, "error", {"message": str(e)})
            await self.broadcast_state({"status": "Error"})
            pump_task.cancel()
            return

        await pump_task
        await self._send(websocket, "final_answer", {"text": answer})
        await self.broadcast_state({"status": "Idle"})

    # ── Client handling ───────────────────────────────────────────────────────

    async def handle_client(self, websocket) -> None:
        self.connected_clients.add(websocket)
        peer = getattr(websocket, "remote_address", "?")
        logger.info(f"Client connected: {peer} | total={len(self.connected_clients)}")

        # Send ambient layer status
        await self._send(websocket, "state_update", {
            "status": "Idle",
            "ambient": {
                "screen_observer": self.screen_observer.mode.value if self.screen_observer else "off",
                "ide_watcher": str(DEFAULT_WATCH_PATH) if self.ide_watcher else "off",
                "proactive_mode": self.proactive_engine.mode if self.proactive_engine else "off",
            }
        })

        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    await self._send(websocket, "error", {"message": "invalid JSON"})
                    continue

                command_type = data.get("type")
                payload = data.get("payload") or {}

                if command_type == "ping":
                    await self._send(websocket, "pong", {})

                elif command_type == "query":
                    text = (payload.get("text") or "").strip()
                    if not text:
                        await self._send(websocket, "error", {"message": "empty query"})
                        continue
                    logger.info(f"Query: {text!r}")
                    await self._process_query(websocket, text)

                elif command_type == "suggestion_action":
                    # User clicked "Accept" on a proactive suggestion
                    suggestion_id = payload.get("id")
                    action = payload.get("action")
                    logger.info(f"User accepted suggestion: {suggestion_id} → {action}")
                    # TODO: route action to appropriate handler
                    await self._send(websocket, "state_update", {"status": f"Executing: {action}"})

                elif command_type == "suggestion_dismiss":
                    suggestion_id = payload.get("id")
                    never_again = payload.get("never_again", False)
                    if self.proactive_engine:
                        self.proactive_engine.dismiss(suggestion_id, never_again)
                    logger.info(f"User dismissed suggestion: {suggestion_id} (never_again={never_again})")

                elif command_type == "suggestion_block":
                    action = payload.get("action")
                    if self.proactive_engine:
                        self.proactive_engine.block_action(action)
                    await self._send(websocket, "state_update", {"blocked_action": action})

                else:
                    await self._send(
                        websocket, "error", {"message": f"unknown type: {command_type}"}
                    )

        except Exception as e:
            logger.warning(f"WebSocket loop ended: {e}")
        finally:
            self.connected_clients.discard(websocket)
            logger.info(f"Client disconnected. total={len(self.connected_clients)}")

    async def start(self) -> None:
        await self._init_ambient_layer()
        logger.info(f"Listening on ws://{self.HOST}:{self.PORT}")
        async with serve(self.handle_client, self.HOST, self.PORT):
            await asyncio.Future()  # run forever

    def shutdown(self):
        """Graceful shutdown of all ambient layers."""
        if self.screen_observer:
            self.screen_observer.stop()
        if self.ide_watcher:
            self.ide_watcher.stop()
        if self.proactive_engine:
            self.proactive_engine.stop()
        self._executor.shutdown(wait=False)
        logger.info("Shutdown complete.")


def main() -> None:
    server = None
    try:
        server = CopartnerServer()
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logger.info("Shutting down.")
    finally:
        if server:
            server.shutdown()


if __name__ == "__main__":
    main()
