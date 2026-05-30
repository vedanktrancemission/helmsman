from __future__ import annotations

from app.config import get_settings
from app.db.models import Workflow
from app.db.session import SessionLocal
from app.runtime.executor import run_persisted

_DEFAULT_AGENT = {
    "name": "Concierge",
    "role": "assistant",
    "system_prompt": "You are a helpful concierge agent reachable over chat. Answer concisely.",
    "model": None,
    "tools": ["calculator", "current_time"],
    "guardrails": {"max_tool_steps": 3},
}


def _default_spec() -> dict:
    return {
        "entry": "Concierge",
        "nodes": [{"name": "Concierge", "agent": _DEFAULT_AGENT}],
        "edges": [{"source": "Concierge", "target": "END"}],
        "recursion_limit": 6,
    }


async def handle_inbound(text: str, conversation_id: str, channel: str = "telegram") -> str:
    settings = get_settings()
    db = SessionLocal()
    try:
        spec = None
        workflow_id = None
        if settings.channel_workflow_id:
            wf = db.get(Workflow, settings.channel_workflow_id)
            if wf:
                spec, workflow_id = wf.graph_spec, wf.id
        if spec is None:
            spec = _default_spec()
        run = await run_persisted(
            db, spec, text, thread_id=conversation_id,
            workflow_id=workflow_id, inbound_channel=channel,
        )
        return run.output or "(no output)"
    finally:
        db.close()
