"""Routes inbound channel messages to the runtime and returns the reply."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Agent, Run, Workflow
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


def _extract_user_message(raw_input: str) -> str:
    for prefix in ("Conversation so far:", "Relevant past context:"):
        if raw_input.startswith(prefix) and "\n\nUser: " in raw_input:
            return raw_input.split("\n\nUser: ", 1)[-1]
    return raw_input


def _conversation_context(db: Session, thread_id: str) -> str:
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
        user_msg = _extract_user_message(run.input)
        turns.append(f"User: {user_msg[:500]}")
        agent_msgs = [
            m for m in run.messages
            if m.role == "agent" and m.recipient == "workflow"
        ]
        if agent_msgs:
            turns.append(f"Assistant: {agent_msgs[-1].content[:500]}")
    return "Conversation so far:\n" + "\n".join(turns) + "\n\nUser: "


def _semantic_context(agent_id: str, query: str) -> str:
    try:
        from app.runtime.memory import get_memory
        mem = get_memory(agent_id)
        results = mem.search(query, k=4)
        if not results:
            return ""
        block = "\n".join(f"- {r}" for r in results)
        return f"Relevant past context:\n{block}\n\nUser: "
    except Exception:
        return ""


def _store_in_memory(agent_id: str, user_msg: str, reply: str) -> None:
    try:
        from app.runtime.memory import get_memory
        mem = get_memory(agent_id)
        mem.add(f"User: {user_msg}")
        mem.add(f"Assistant: {reply}")
    except Exception:
        pass


def _get_channel_agent(db: Session, spec: dict) -> Agent | None:
    nodes = spec.get("nodes", [])
    if not nodes:
        return None
    agent_id = nodes[0].get("agent_id")
    if not agent_id:
        return None
    return db.get(Agent, agent_id)


async def handle_inbound(text: str, conversation_id: str, channel: str = "telegram") -> str:
    settings = get_settings()
    db = SessionLocal()
    try:
        spec = None
        workflow_id = None
        channel_agent: Agent | None = None

        if settings.channel_workflow_id:
            wf = db.get(Workflow, settings.channel_workflow_id)
            if wf:
                spec, workflow_id = wf.graph_spec, wf.id
                channel_agent = _get_channel_agent(db, spec)

        if spec is None:
            spec = _default_spec()

        memory_type = "none"
        if channel_agent and channel_agent.memory_config:
            memory_type = channel_agent.memory_config.get("type", "none")

        if memory_type == "semantic" and channel_agent:
            context = _semantic_context(channel_agent.id, text)
        else:
            context = _conversation_context(db, conversation_id)

        input_with_context = f"{context}{text}" if context else text

        run = await run_persisted(
            db, spec, input_with_context, thread_id=conversation_id,
            workflow_id=workflow_id, inbound_channel=channel,
        )

        if run.status == "failed":
            return "Sorry, I ran into an issue processing your message. Please try again."

        reply = run.output or "I processed your message but had nothing to say. Please try again."

        if memory_type == "semantic" and channel_agent:
            _store_in_memory(channel_agent.id, text, reply)

        return reply
    finally:
        db.close()
