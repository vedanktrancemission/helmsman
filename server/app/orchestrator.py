"""Routes inbound channel messages to the runtime and returns the reply."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Run, Workflow
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

_HISTORY_TURNS = 6


def _default_spec() -> dict:
    return {
        "entry": "Concierge",
        "nodes": [{"name": "Concierge", "agent": _DEFAULT_AGENT}],
        "edges": [{"source": "Concierge", "target": "END"}],
        "recursion_limit": 6,
    }


def _conversation_context(db: Session, thread_id: str) -> str:
    """Return the last N turns for this thread as a context prefix."""
    past = (
        db.query(Run)
        .filter(Run.thread_id == thread_id, Run.status == "completed")
        .order_by(Run.started_at.desc())
        .limit(_HISTORY_TURNS)
        .all()
    )
    if not past:
        return ""
    turns = []
    for run in reversed(past):
        turns.append(f"User: {run.input}")
        agent_msgs = [
            m for m in run.messages
            if m.role == "agent" and m.recipient == "workflow"
        ]
        if agent_msgs:
            turns.append(f"Assistant: {agent_msgs[-1].content}")
    return "Conversation so far:\n" + "\n".join(turns) + "\n\nUser: "


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

        context = _conversation_context(db, conversation_id)
        input_with_context = f"{context}{text}" if context else text

        run = await run_persisted(
            db, spec, input_with_context, thread_id=conversation_id,
            workflow_id=workflow_id, inbound_channel=channel,
        )
        return run.output or "(no output)"
    finally:
        db.close()
