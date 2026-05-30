from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol


@dataclass
class InboundMessage:
    conversation_id: str
    text: str
    sender: str = "human"


OnMessage = Callable[[InboundMessage], Awaitable[str]]


class Channel(Protocol):
    name: str

    async def start(self, on_message: OnMessage) -> None:
        ...

    async def send(self, conversation_id: str, text: str) -> None:
        ...
