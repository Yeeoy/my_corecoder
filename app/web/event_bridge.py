import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


def _jsonable(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return str(value)


class WebEventBridge:
    def __init__(self):
        self.clients: set[WebSocket] = set()
        self.loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.clients.add(websocket)

        await websocket.send_json(
            {
                "type": "websocket_connected",
                "payload": {
                    "message": "Connected to CoreCoder runtime.",
                },
            }
        )

    def disconnect(self, websocket: WebSocket) -> None:
        self.clients.discard(websocket)

    def publish(self, event_type: str, payload: dict | None = None) -> None:
        event = {
            "type": event_type,
            "payload": _jsonable(payload or {}),
        }

        logger.debug("publish: %s, clients=%d", event_type, len(self.clients))

        if not self.loop or not self.loop.is_running():
            logger.warning("publish skipped: loop not running")
            return

        asyncio.run_coroutine_threadsafe(self._broadcast(event), self.loop)

    def handle(self, payload: dict) -> None:
        raw_event = payload.get("_event", "unknown")
        event_name = getattr(raw_event, "value", str(raw_event))

        clean_payload = dict(payload)
        clean_payload["_event"] = event_name

        self.publish(
            "core_event",
            {"event": event_name, "payload": clean_payload},
        )

    async def _broadcast(self, event: dict) -> None:
        dead_clients: list[WebSocket] = []

        logger.debug("broadcast: %s -> %d clients", event["type"], len(self.clients))

        for client in list(self.clients):
            try:
                await client.send_json(event)
            except Exception as e:
                logger.warning("send failed: %s", e)
                dead_clients.append(client)

        for client in dead_clients:
            self.disconnect(client)
