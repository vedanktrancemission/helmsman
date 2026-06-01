"""FastAPI app: API routers, CORS, DB init, Telegram background task, and cron scheduler."""
from __future__ import annotations

import asyncio
import contextlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agents, chat, runs, templates, workflows, ws
from app.channels.telegram import TelegramChannel
from app.config import get_settings
from app.db.session import SessionLocal, init_db
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
app.include_router(chat.router)
app.include_router(workflows.router)
app.include_router(runs.router)
app.include_router(templates.router)
app.include_router(ws.router)

_telegram: TelegramChannel | None = None
_telegram_task: asyncio.Task | None = None
_scheduler = None


@app.get("/health")
def health():
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "bus": settings.bus_backend,
        "telegram": bool(settings.telegram_bot_token),
    }


def _make_scheduled_job(agent_id: str, agent_name: str, role: str, system_prompt: str,
                        model: str, tools: list, guardrails: dict, prompt: str):
    async def job():
        from app.runtime.executor import run_persisted
        spec = {
            "entry": agent_name,
            "nodes": [{
                "name": agent_name,
                "agent": {
                    "name": agent_name,
                    "role": role,
                    "system_prompt": system_prompt,
                    "model": model,
                    "tools": tools,
                    "guardrails": guardrails,
                },
            }],
            "edges": [{"source": agent_name, "target": "END"}],
            "recursion_limit": 10,
        }
        db = SessionLocal()
        try:
            await run_persisted(db, spec, prompt, thread_id=f"schedule:{agent_id}", inbound_channel="schedule")
        finally:
            db.close()
    return job


def _start_scheduler():
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = AsyncIOScheduler()
    db = SessionLocal()
    try:
        from app.db.models import Agent
        agents_list = db.query(Agent).all()
        count = 0
        for agent in agents_list:
            sched = agent.schedule or {}
            cron_expr = sched.get("cron", "").strip()
            if not cron_expr:
                continue
            prompt = sched.get("prompt", "Run your scheduled task.")
            try:
                trigger = CronTrigger.from_crontab(cron_expr)
                job_fn = _make_scheduled_job(
                    agent.id, agent.name, agent.role or "",
                    agent.system_prompt or "", agent.model or "fake",
                    agent.tools or [], agent.guardrails or {}, prompt,
                )
                scheduler.add_job(job_fn, trigger, id=f"agent:{agent.id}", replace_existing=True)
                count += 1
            except Exception:
                pass
        if count:
            scheduler.start()
    finally:
        db.close()
    return scheduler


@app.on_event("startup")
async def on_startup() -> None:
    init_db()
    global _telegram, _telegram_task, _scheduler

    _scheduler = _start_scheduler()

    if settings.telegram_bot_token:
        _telegram = TelegramChannel(settings.telegram_bot_token)

        async def on_msg(inbound) -> str:
            return await handle_inbound(inbound.text, inbound.conversation_id, channel="telegram")

        _telegram_task = asyncio.create_task(_telegram.start(on_msg))


@app.on_event("shutdown")
async def on_shutdown() -> None:
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    if _telegram:
        _telegram.stop()
    if _telegram_task:
        _telegram_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _telegram_task
