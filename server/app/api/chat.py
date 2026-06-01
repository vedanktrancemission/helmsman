"""Chat endpoint — single-agent multi-turn conversation."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import Agent, Run
from app.db.session import get_db
from app.runtime.executor import run_persisted

router = APIRouter(prefix="/api/chat", tags=["chat"])

_HISTORY_TURNS = 6


class ChatRequest(BaseModel):
    agent_id: str
    message: str
    thread_id: str = ""


class ChatResponse(BaseModel):
    reply: str
    thread_id: str
    run_id: str


class ChatHistoryMessage(BaseModel):
    role: str
    content: str


def _extract_user_message(raw_input: str) -> str:
    if raw_input.startswith("Conversation so far:") and "\n\nUser: " in raw_input:
        return raw_input.split("\n\nUser: ", 1)[-1]
    if raw_input.startswith("Relevant past context:") and "\n\nUser: " in raw_input:
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
        agent_msgs = [m for m in run.messages if m.role == "agent" and m.recipient == "workflow"]
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


@router.post("", response_model=ChatResponse)
async def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    agent = db.get(Agent, payload.agent_id)
    if not agent:
        raise HTTPException(404, "agent not found")

    thread_id = payload.thread_id or str(uuid.uuid4())
    memory_type = (agent.memory_config or {}).get("type", "none")

    if memory_type == "semantic":
        context = _semantic_context(agent.id, payload.message)
    else:
        context = _conversation_context(db, thread_id)

    input_with_context = f"{context}{payload.message}" if context else payload.message

    spec = {
        "entry": agent.name,
        "nodes": [
            {
                "name": agent.name,
                "agent": {
                    "name": agent.name,
                    "role": agent.role,
                    "system_prompt": agent.system_prompt,
                    "model": agent.model,
                    "tools": agent.tools,
                    "guardrails": agent.guardrails,
                },
            }
        ],
        "edges": [{"source": agent.name, "target": "END"}],
        "recursion_limit": 10,
    }

    run = await run_persisted(
        db, spec, input_with_context, thread_id=thread_id, inbound_channel="chat"
    )

    if run.status == "failed":
        raise HTTPException(500, run.error or "run failed")

    reply = run.output or "(no response)"

    if memory_type == "semantic":
        _store_in_memory(agent.id, payload.message, reply)

    return ChatResponse(reply=reply, thread_id=thread_id, run_id=run.id)


@router.get("/history", response_model=list[ChatHistoryMessage])
def get_chat_history(thread_id: str, db: Session = Depends(get_db)):
    """Return ordered user/agent messages for a thread."""
    runs = (
        db.query(Run)
        .filter(Run.thread_id == thread_id, Run.status == "completed")
        .order_by(Run.started_at.asc())
        .all()
    )
    result = []
    for run in runs:
        user_msg = _extract_user_message(run.input)
        result.append({"role": "user", "content": user_msg})
        agent_msgs = [m for m in run.messages if m.role == "agent" and m.recipient == "workflow"]
        if agent_msgs:
            result.append({"role": "agent", "content": agent_msgs[-1].content})
    return result
