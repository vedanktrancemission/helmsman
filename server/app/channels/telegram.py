"""Telegram long-polling channel adapter."""
from __future__ import annotations

import asyncio
import re

import httpx

from app.channels.base import Channel, InboundMessage, OnMessage


def _md_to_telegram_html(text: str) -> str:
    """Convert common markdown to Telegram HTML (parse_mode=HTML)."""
    # Escape HTML special chars first
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Code blocks (``` ... ```) → <pre>
    text = re.sub(r"```(?:\w+)?\n?(.*?)```", lambda m: f"<pre>{m.group(1).strip()}</pre>", text, flags=re.DOTALL)

    # Inline code → <code>
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    # Bold **text** or __text__ → <b>
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)

    # Italic *text* or _text_ → <i>
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    text = re.sub(r"_(.+?)_", r"<i>\1</i>", text)

    # Headings ### → <b>
    text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    # Horizontal rules --- → blank line
    text = re.sub(r"^[-*_]{3,}$", "", text, flags=re.MULTILINE)

    # Tables → strip to plain rows (Telegram doesn't support tables)
    lines = text.splitlines()
    clean_lines = []
    for line in lines:
        if re.match(r"^\|[-| :]+\|$", line.strip()):
            continue  # skip separator rows
        if line.strip().startswith("|") and line.strip().endswith("|"):
            # Extract cell text, strip pipes and extra spaces
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            clean_lines.append("  •  ".join(cells))
        else:
            clean_lines.append(line)
    text = "\n".join(clean_lines)

    # Remove excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


class TelegramChannel(Channel):
    name = "telegram"

    def __init__(self, bot_token: str) -> None:
        self._token = bot_token
        self._base = f"https://api.telegram.org/bot{bot_token}"
        self._offset = 0
        self._running = False

    async def send(self, conversation_id: str, text: str) -> None:
        html = _md_to_telegram_html(text)
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{self._base}/sendMessage",
                json={"chat_id": conversation_id, "text": html, "parse_mode": "HTML"},
            )
            # Fallback to plain text if HTML parse fails
            if resp.status_code != 200:
                await client.post(
                    f"{self._base}/sendMessage",
                    json={"chat_id": conversation_id, "text": text},
                )

    async def _typing_loop(self, conversation_id: str, stop_event: asyncio.Event) -> None:
        """Send 'typing' indicator every 4 seconds until stop_event is set."""
        async with httpx.AsyncClient(timeout=10) as client:
            while not stop_event.is_set():
                try:
                    await client.post(
                        f"{self._base}/sendChatAction",
                        json={"chat_id": conversation_id, "action": "typing"},
                    )
                except Exception:  # noqa: BLE001
                    pass
                await asyncio.sleep(4)

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
                    stop_typing = asyncio.Event()
                    typing_task = asyncio.create_task(
                        self._typing_loop(inbound.conversation_id, stop_typing)
                    )
                    try:
                        reply = await on_message(inbound)
                        if reply:
                            await self.send(inbound.conversation_id, reply)
                    except Exception as exc:  # noqa: BLE001
                        await self.send(inbound.conversation_id, f"⚠️ error: {exc}")
                    finally:
                        stop_typing.set()
                        typing_task.cancel()

    def stop(self) -> None:
        self._running = False
