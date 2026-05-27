"""
Copartner WebSocket Server — Full Foundation
==============================================
Bridges the React/Tauri frontend (ws://127.0.0.1:8765) to the Python brain.

AMBIENT MODE: ScreenObserver + IDEWatcher + ProactiveEngine on boot.
RICH EVENTS: tool executions, thinking traces, token usage, budget, memory.

Run as:
    python -m core.copartner_server          (preferred)
    python core/copartner_server.py          (also works)
"""

from __future__ import annotations

import sys
import asyncio
import json
import logging
import base64
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any
from datetime import datetime

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
from core.thought_controller import ThoughtController, State  # noqa: E402
from core.proactive_engine import ProactiveEngine, Observation  # noqa: E402
from perception.screen_observer import ScreenObserver, ObserverMode  # noqa: E402
from perception.ide_watcher import IDEWatcher  # noqa: E402
from action.file_ops import file_read, file_list  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("Copartner.Server")

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

        self.screen_observer: ScreenObserver | None = None
        self.ide_watcher: IDEWatcher | None = None
        self.proactive_engine: ProactiveEngine | None = None

        # Ambient state tracking
        self._ambient_active = False
        self._ambient_error_count = 0
        self._ambient_status_message = "Copartner ready"

        # Chat history persistence
        self._chat_log_path = _PROJECT_ROOT / "data" / "chat_history.jsonl"
        self._chat_log_path.parent.mkdir(parents=True, exist_ok=True)

    async def _init_ambient_layer(self):
        gemini_client = self.thought_controller.gemini
        behavior_engine = self.thought_controller.behavior

        self.proactive_engine = ProactiveEngine(
            gemini_client=gemini_client,
            mode="advisory",
            confidence_threshold=0.70,
            cooldown_sec=30.0,
            on_suggestion=self._on_proactive_suggestion,
        )
        self.proactive_engine.start()

        self.screen_observer = ScreenObserver(
            gemini_client=gemini_client,
            mode=ObserverMode.ADVISORY,
            capture_interval_sec=5.0,
            diff_threshold=0.15,
            on_change=self._on_screen_change,
        )
        self.screen_observer.start()

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
        import time
        if self.proactive_engine:
            self.proactive_engine.observe(Observation(
                source="screen", event_type="change", content=analysis,
                timestamp=time.time(), metadata={},
            ))
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.call_soon_threadsafe(asyncio.create_task, self.broadcast_state({
                    "ambient": {"screen_last_analysis": analysis[:200]},
                }))
        except RuntimeError:
            pass

    def _on_file_create(self, path: str, content: str):
        import time
        if self.proactive_engine:
            self.proactive_engine.observe(Observation(
                source="ide", event_type="create", content=Path(path).name,
                timestamp=time.time(),
                metadata={"path": path, "content_preview": content[:200]},
            ))
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.call_soon_threadsafe(asyncio.create_task, self.broadcast_state({
                    "ambient": {"last_file_event": f"Created {Path(path).name}"},
                }))
        except RuntimeError:
            pass

    def _on_file_modify(self, path: str, content: str):
        import time
        if self.proactive_engine:
            self.proactive_engine.observe(Observation(
                source="ide", event_type="modify", content=Path(path).name,
                timestamp=time.time(),
                metadata={"path": path, "content_preview": content[:200]},
            ))
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.call_soon_threadsafe(asyncio.create_task, self.broadcast_state({
                    "ambient": {"last_file_event": f"Modified {Path(path).name}"},
                }))
        except RuntimeError:
            pass

    def _on_file_delete(self, path: str):
        import time
        if self.proactive_engine:
            self.proactive_engine.observe(Observation(
                source="ide", event_type="delete", content=Path(path).name,
                timestamp=time.time(),
                metadata={"path": path},
            ))
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.call_soon_threadsafe(asyncio.create_task, self.broadcast_state({
                    "ambient": {"last_file_event": f"Deleted {Path(path).name}"},
                }))
        except RuntimeError:
            pass

    def _on_proactive_suggestion(self, suggestion):
        asyncio.create_task(self._broadcast_suggestion(suggestion))

    async def _broadcast_suggestion(self, suggestion):
        if not self.connected_clients:
            return
        payload = {
            "id": suggestion.id, "text": suggestion.text,
            "action": suggestion.action, "confidence": suggestion.confidence,
        }
        message = json.dumps({"type": "proactive_suggestion", "payload": payload})
        await asyncio.gather(*(c.send(message) for c in self.connected_clients), return_exceptions=True)
        logger.info(f"Broadcasted suggestion to {len(self.connected_clients)} client(s)")

    # ── WebSocket helpers ─────────────────────────────────────────────────────

    async def broadcast_state(self, state_update: Dict[str, Any]) -> None:
        if not self.connected_clients:
            return
        message = json.dumps({"type": "state_update", "payload": state_update})
        await asyncio.gather(*(c.send(message) for c in self.connected_clients), return_exceptions=True)

    async def broadcast_ambient_status(self, state: str, message: str, error_count: int | None = None) -> None:
        """Broadcast ambient status to all connected clients for the bar UI."""
        if not self.connected_clients:
            return
        payload = {"state": state, "message": message}
        if error_count is not None:
            payload["error_count"] = error_count
        msg = json.dumps({"type": "ambient_status", "payload": payload})
        await asyncio.gather(*(c.send(msg) for c in self.connected_clients), return_exceptions=True)

    async def broadcast_urgency_alert(self, message: str, score: int, source: str = "") -> None:
        """Broadcast urgent alert that should auto-expand the bar."""
        if not self.connected_clients:
            return
        payload = {"message": message, "score": score, "source": source}
        msg = json.dumps({"type": "urgency_alert", "payload": payload})
        await asyncio.gather(*(c.send(msg) for c in self.connected_clients), return_exceptions=True)
        logger.info(f"Urgency alert broadcasted: {message} (score={score})")

    async def _send(self, websocket, type_: str, payload: Dict[str, Any]) -> None:
        try:
            await websocket.send(json.dumps({"type": type_, "payload": payload}))
        except Exception as e:
            logger.warning(f"send failed: {e}")

    # ── Chat persistence ──────────────────────────────────────────────────────

    def _log_chat(self, role: str, text: str, metadata: dict | None = None):
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "role": role,
            "text": text[:2000],
            "metadata": metadata or {},
        }
        try:
            with open(self._chat_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.warning(f"Chat log write failed: {e}")

    def _load_chat_history(self, limit: int = 100) -> list[dict]:
        history = []
        if not self._chat_log_path.exists():
            return history
        try:
            with open(self._chat_log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            history.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.warning(f"Chat log read failed: {e}")
        return history[-limit:]

    # ── Query processing with rich events ─────────────────────────────────────

    async def _process_query(self, websocket, query_text: str) -> None:
        await self.broadcast_state({"status": "Thinking"})
        self._log_chat("user", query_text)

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        tool_queue: asyncio.Queue = asyncio.Queue()
        state_queue: asyncio.Queue = asyncio.Queue()

        def stream_cb(token: str) -> None:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, token)
            except RuntimeError:
                pass

        # Monkey-patch tool executor to broadcast tool events
        original_execute = self.thought_controller.tools.execute
        def tool_cb(tag: str, content: str) -> str:
            loop.call_soon_threadsafe(tool_queue.put_nowait, {
                "tag": tag, "status": "start", "content": content[:200],
            })
            result = original_execute(tag, content)
            loop.call_soon_threadsafe(tool_queue.put_nowait, {
                "tag": tag, "status": "end", "result_preview": str(result)[:300],
            })
            return result

        self.thought_controller.tools.execute = tool_cb

        def run_brain() -> dict:
            answer = self.thought_controller.run(query_text, stream_callback=stream_cb)
            # Gather metadata
            tc = self.thought_controller
            budget = tc.budget
            router = tc.router
            memory = tc.memory

            meta = {
                "answer": answer,
                "steps": getattr(run_brain, '_steps', 1),
                "model_used": "pro" if getattr(run_brain, '_use_pro', False) else "flash",
                "state": tc.state.name,
            }

            if budget:
                meta["budget"] = budget.status()
            if memory:
                meta["memory_stats"] = memory.stats()
            if router and hasattr(router, '_last_decision'):
                d = router._last_decision
                meta["route"] = {"model": d.model, "intent": d.intent, "rationale": d.rationale}

            return meta

        future = loop.run_in_executor(self._executor, run_brain)

        # Stream tokens
        async def pump_tokens():
            while not future.done() or not queue.empty():
                try:
                    token = await asyncio.wait_for(queue.get(), timeout=0.2)
                    await self._send(websocket, "stream_chunk", {"text": token})
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.warning(f"Token pump error: {e}")
                    break

        # Stream tool events
        async def pump_tools():
            while not future.done() or not tool_queue.empty():
                try:
                    event = await asyncio.wait_for(tool_queue.get(), timeout=0.5)
                    await self._send(websocket, "tool_event", event)
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.warning(f"Tool pump error: {e}")
                    break

        pump_task = asyncio.create_task(pump_tokens())
        tool_task = asyncio.create_task(pump_tools())

        try:
            meta = await future
        except Exception as e:
            logger.exception("Brain error")
            await self._send(websocket, "error", {"message": str(e)})
            await self.broadcast_state({"status": "Error"})
            pump_task.cancel()
            tool_task.cancel()
            self.thought_controller.tools.execute = original_execute
            return

        await pump_task
        await tool_task

        # Restore original execute
        self.thought_controller.tools.execute = original_execute

        answer = meta.get("answer", "")
        # Strip final_answer tags for display
        answer = answer.replace("<final_answer>", "").replace("</final_answer>", "").strip()

        await self._send(websocket, "final_answer", {"text": answer})

        # Send rich metadata
        if "budget" in meta:
            await self._send(websocket, "token_usage", meta["budget"])
        if "memory_stats" in meta:
            await self._send(websocket, "memory_stats", meta["memory_stats"])
        if "route" in meta:
            await self._send(websocket, "route_decision", meta["route"])

        await self.broadcast_state({"status": "Idle"})
        self._log_chat("agent", answer, {"budget": meta.get("budget"), "route": meta.get("route")})

    # ── Client handling ───────────────────────────────────────────────────────

    async def handle_client(self, websocket) -> None:
        self.connected_clients.add(websocket)
        peer = getattr(websocket, "remote_address", "?")
        logger.info(f"Client connected: {peer} | total={len(self.connected_clients)}")

        # Send ambient layer status + initial data
        await self._send(websocket, "state_update", {
            "status": "Idle",
            "ambient": {
                "screen_observer": self.screen_observer.mode.value if self.screen_observer else "off",
                "ide_watcher": str(DEFAULT_WATCH_PATH) if self.ide_watcher else "off",
                "proactive_mode": self.proactive_engine.mode if self.proactive_engine else "off",
            }
        })

        # Send budget status if available
        if self.thought_controller.budget:
            await self._send(websocket, "token_usage", self.thought_controller.budget.status())

        # Send memory stats if available
        if self.thought_controller.memory:
            await self._send(websocket, "memory_stats", self.thought_controller.memory.stats())

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

                elif command_type == "get_budget":
                    if self.thought_controller.budget:
                        await self._send(websocket, "token_usage", self.thought_controller.budget.status())

                elif command_type == "get_memory":
                    if self.thought_controller.memory:
                        query = payload.get("query", "")
                        mem_type = payload.get("memory_type")
                        n = payload.get("n_results", 10)
                        results = self.thought_controller.memory.recall(query, memory_type=mem_type, n_results=n)
                        await self._send(websocket, "memory_data", {"results": results, "query": query})
                    else:
                        await self._send(websocket, "memory_data", {"results": [], "query": payload.get("query", "")})

                elif command_type == "list_files":
                    path = payload.get("path", ".")
                    recursive = payload.get("recursive", False)
                    result = file_list(path, base_dir=DEFAULT_WATCH_PATH, recursive=recursive)
                    await self._send(websocket, "file_data", result)

                elif command_type == "read_file":
                    path = payload.get("path", "")
                    if path:
                        result = file_read(path, base_dir=DEFAULT_WATCH_PATH)
                        await self._send(websocket, "file_data", result)

                elif command_type == "get_chat_history":
                    limit = payload.get("limit", 50)
                    history = self._load_chat_history(limit)
                    await self._send(websocket, "chat_history", {"entries": history})

                elif command_type == "capture_screen":
                    if self.screen_observer:
                        img_bytes = self.screen_observer.capture()
                        if img_bytes:
                            b64 = base64.b64encode(img_bytes).decode("utf-8")
                            await self._send(websocket, "screen_capture", {"image_b64": b64})
                        else:
                            await self._send(websocket, "error", {"message": "Screen capture failed"})
                    else:
                        await self._send(websocket, "error", {"message": "Screen observer not running"})

                elif command_type == "get_stats":
                    stats = {"status": "ok"}
                    if self.thought_controller.budget:
                        stats["budget"] = self.thought_controller.budget.status()
                    if self.thought_controller.memory:
                        stats["memory"] = self.thought_controller.memory.stats()
                    if self.proactive_engine:
                        stats["proactive"] = self.proactive_engine.get_stats()
                    await self._send(websocket, "system_stats", stats)

                elif command_type == "suggestion_action":
                    suggestion_id = payload.get("id")
                    action = payload.get("action")
                    logger.info(f"User accepted suggestion: {suggestion_id} → {action}")
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

                elif command_type == "ambient_toggle":
                    active = payload.get("active", False)
                    self._ambient_active = active
                    if active:
                        if self.screen_observer and not self.screen_observer._running:
                            self.screen_observer.start()
                        if self.ide_watcher and not self.ide_watcher._running:
                            self.ide_watcher.start()
                        if self.proactive_engine and not self.proactive_engine._running:
                            self.proactive_engine.start()
                        msg = "Ambient monitoring active"
                        state = "watching"
                    else:
                        if self.screen_observer:
                            self.screen_observer.stop()
                        if self.ide_watcher:
                            self.ide_watcher.stop()
                        if self.proactive_engine:
                            self.proactive_engine.stop()
                        msg = "Ambient monitoring paused"
                        state = "idle"
                    logger.info(f"Ambient toggled: {active}")
                    await self.broadcast_ambient_status(state, msg, self._ambient_error_count)

                else:
                    await self._send(websocket, "error", {"message": f"unknown type: {command_type}"})

        except Exception as e:
            logger.warning(f"WebSocket loop ended: {e}")
        finally:
            self.connected_clients.discard(websocket)
            logger.info(f"Client disconnected. total={len(self.connected_clients)}")

    async def start(self) -> None:
        await self._init_ambient_layer()
        logger.info(f"Listening on ws://{self.HOST}:{self.PORT}")
        async with serve(self.handle_client, self.HOST, self.PORT):
            await asyncio.Future()

    def shutdown(self):
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
