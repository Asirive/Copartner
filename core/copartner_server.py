import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from websockets.server import serve
from typing import Dict, Any

from core.thought_controller import ThoughtController

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Copartner.Server")

class CopartnerServer:
    def __init__(self):
        self.host = "127.0.0.1"
        self.port = 8765
        self.thought_controller = ThoughtController.create()
        self.connected_clients = set()
        self._executor = ThreadPoolExecutor(max_workers=4)

    async def broadcast_state(self, state_update: Dict[str, Any]):
        if not self.connected_clients:
            return
        message = json.dumps({"type": "state_update", "payload": state_update})
        await asyncio.gather(*[client.send(message) for client in self.connected_clients], return_exceptions=True)

    async def handle_client(self, websocket):
        self.connected_clients.add(websocket)
        logger.info(f"Client connected. Total clients: {len(self.connected_clients)}")
        try:
            async for message in websocket:
                data = json.loads(message)
                command_type = data.get("type")
                payload = data.get("payload", {})

                if command_type == "query":
                    query_text = payload.get("text", "")
                    logger.info(f"Received query: {query_text}")
                    await self.broadcast_state({"status": "Thinking", "model": "gemini-pro"})

                    try:
                        # Run blocking thought controller in thread pool so the event loop stays free
                        loop = asyncio.get_running_loop()
                        final_answer = await loop.run_in_executor(
                            self._executor,
                            self.thought_controller.run,
                            query_text
                        )

                        await websocket.send(json.dumps({
                            "type": "final_answer",
                            "payload": {"text": final_answer}
                        }))
                        await self.broadcast_state({"status": "Idle", "model": None})

                    except Exception as e:
                        logger.error(f"Error processing query: {e}", exc_info=True)
                        await websocket.send(json.dumps({
                            "type": "error",
                            "payload": {"message": str(e)}
                        }))
                        await self.broadcast_state({"status": "Error", "model": None})

        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            self.connected_clients.discard(websocket)
            logger.info("Client disconnected.")

    async def start(self):
        logger.info(f"Starting Copartner WebSocket Server on ws://{self.host}:{self.port}")
        async with serve(self.handle_client, self.host, self.port):
            await asyncio.Future()  # run forever

if __name__ == "__main__":
    server = CopartnerServer()
    asyncio.run(server.start())
