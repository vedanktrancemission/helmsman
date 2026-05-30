"""Telegram long-polling channel adapter."""
from __future__ import annotations

import asyncio

import httpx

from app.channels.base import Channel, InboundMessage, OnMessage


class TelegramChannel(Channel):
    name = "telegram"

    def __init__(self, bot_token: str) -> None:
        self._token = bot_token
        self._base = f"https://api.telegram.org/bot{bot_token}"
        self._offset = 0
        self._running = False

    async def send(self, conversation_id: str, text: str) -> None:
        async with httpx.AsyncClient(timeout=20) as client:
            await client.post(
                f"{self._base}/sendMessage",
                json={"chat_id": conversation_id, "text": text},
            )

    async def start(self, on_message: OnMessage) -> None:
        self._running = True
        async with httpx.AsyncClient(timeout=70) as client:
            while self._running:
                try:
                    resp = await client.get(
                        f"{self._base}/getUpdates",
                        params={"offset": self._offset, "timeout": 50},
                    )
                    data = resp.json()
                except Exception:  # noqa: BLE001
                    await asyncio.sleep(2)
                    continue

                for update in data.get("result", []):
                    self._offset = update["update_id"] + 1
                    msg = update.get("message") or {}
                    text = msg.get("text")
                    chat = msg.get("chat", {})
                    if not text or "id" not in chat:
                        continue
                    inbound = InboundMessage(conversation_id=str(chat["id"]), text=text)
                    try:
                        reply = await on_message(inbound)
                        if reply:
                            await self.send(inbound.conversation_id, reply)
                    except Exception as exc:  # noqa: BLE001
                        await self.send(inbound.conversation_id, f"⚠️ error: {exc}")

    def stop(self) -> None:
        self._running = False
