from __future__ import annotations

import asyncio
import contextlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agents, runs, templates, workflows, ws
from app.channels.telegram import TelegramChannel
from app.config import get_settings
from app.db.session import init_db
from app.orchestrator import handle_inbound

settings = get_settings()

init_db()

app = FastAPI(title="Helmsman — AI Agent Orchestration Platform", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")] or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents.router)
app.include_router(workflows.router)
app.include_router(runs.router)
app.include_router(templates.router)
app.include_router(ws.router)

_telegram: TelegramChannel | None = None
_telegram_task: asyncio.Task | None = None


@app.get("/health")
def health():
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "bus": settings.bus_backend,
        "telegram": bool(settings.telegram_bot_token),
    }


@app.on_event("startup")
async def on_startup() -> None:
    init_db()
    global _telegram, _telegram_task
    if settings.telegram_bot_token:
        _telegram = TelegramChannel(settings.telegram_bot_token)

        async def on_msg(inbound) -> str:
            return await handle_inbound(inbound.text, inbound.conversation_id, channel="telegram")

        _telegram_task = asyncio.create_task(_telegram.start(on_msg))


@app.on_event("shutdown")
async def on_shutdown() -> None:
    if _telegram:
        _telegram.stop()
    if _telegram_task:
        _telegram_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _telegram_task
