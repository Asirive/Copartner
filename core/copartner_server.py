import asyncio
import json
import logging
from websockets.server import serve
from typing import Dict, Any

from core.thought_controller import ThoughtController
from core.intent_router import IntentRouter
from core.model_router import ModelRouter
from memory.memory_manager import MemoryManager
from config import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Copartner.Server")

class CopartnerServer:
    def __init__(self):
        self.host = "127.0.0.1"
        self.port = 8765
        self.thought_controller = ThoughtController.create()
        self.connected_clients = set()

    async def broadcast_state(self, state_update: Dict[str, Any]):
        """Broadcast status updates (e.g., token usage, active models) to all connected UI clients."""
        if not self.connected_clients:
            return
            
        message = json.dumps({"type": "state_update", "payload": state_update})
        await asyncio.gather(*[client.send(message) for client in self.connected_clients])

    async def stream_output(self, websocket, text: str):
        """Stream generated text chunks back to the client."""
        await websocket.send(json.dumps({
            "type": "stream_chunk",
            "payload": {"text": text}
        }))

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
                    
                    # Notify UI that processing has started
                    await self.broadcast_state({"status": "Thinking", "model": "gemini-pro"})
                    
                    # Execute the thought loop (synchronous call wrapped in executor if needed, 
                    # but for MVP we can run it and collect output. To truly stream, we'd need async thought_controller)
                    
                    try:
                        # In a fully async version, this would be await self.thought_controller.run_async(query_text)
                        # For now, we simulate streaming the final answer.
                        # (TODO: integrate true token streaming via thought_controller's callbacks)
                        final_answer = self.thought_controller.run(query_text)
                        
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
            self.connected_clients.remove(websocket)
            logger.info("Client disconnected.")

    async def start(self):
        logger.info(f"Starting Copartner WebSocket Server on ws://{self.host}:{self.port}")
        async with serve(self.handle_client, self.host, self.port):
            await asyncio.Future()  # run forever

if __name__ == "__main__":
    server = CopartnerServer()
    asyncio.run(server.start())
