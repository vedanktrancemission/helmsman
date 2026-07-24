"""Executes a graph_spec and persists the run, messages, and token usage."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Agent, Message, Run, Usage, Workflow
from app.runtime.bus import get_bus
from app.runtime.callbacks import CostTracker
from app.runtime.compiler import compile_graph, recursion_limit
from app.runtime.nodes import ExecContext


def agent_to_config(agent: Agent) -> dict:
    return {
        "id": agent.id,
        "name": agent.name,
        "role": agent.role,
        "system_prompt": agent.system_prompt,
        "model": agent.model,
        "tools": agent.tools or [],
        "guardrails": agent.guardrails or {},
        "interaction_rules": agent.interaction_rules or {},
        "skills": agent.skills or [],
        "memory_config": agent.memory_config or {},
    }


def _agent_lookup(db: Session) -> dict[str, dict]:
    return {a.id: agent_to_config(a) for a in db.query(Agent).all()}


async def execute_spec(
    *,
    spec: dict,
    input_text: str,
    run_id: str,
    agent_lookup: dict[str, dict] | None = None,
    token_ceiling: int | None = None,
) -> dict:
    """Execute a graph_spec and return final output, messages, and usage."""
    settings = get_settings()
    bus = get_bus()
    cost = CostTracker(token_ceiling=token_ceiling or settings.default_run_token_ceiling)
    collected: list[dict] = []

    async def emit(event: dict) -> None:
        await bus.publish(event)

    async def record_message(msg: dict) -> None:
        msg = {**msg, "run_id": run_id}
        collected.append(msg)
        await bus.publish({"type": "agent_message", "run_id": run_id, **msg})

    ctx = ExecContext(run_id=run_id, cost=cost, emit=emit, record_message=record_message)
    app = compile_graph(spec, ctx, agent_lookup or {})

    await emit({"type": "run_start", "run_id": run_id, "input": input_text})
    state = {"input": input_text, "history": [], "outputs": {}, "final": "", "steps": 0}
    result = await app.ainvoke(state, config={"recursion_limit": recursion_limit(spec)})
    final = result.get("final", "")
    await emit(
        {
            "type": "run_end",
            "run_id": run_id,
            "output": final,
            "total_cost_usd": cost.total_cost,
            "total_tokens": cost.total_tokens,
        }
    )
    return {
        "final": final,
        "messages": collected,
        "usage": cost.records,
        "cost": cost.total_cost,
        "tokens": cost.total_tokens,
    }


async def run_persisted(
    db: Session,
    spec: dict,
    input_text: str,
    thread_id: str = "default",
    workflow_id: str | None = None,
    inbound_channel: str | None = None,
) -> Run:
    """Create a Run record, execute the spec, and persist all results."""
    run = Run(workflow_id=workflow_id, thread_id=thread_id, status="running", input=input_text)
    db.add(run)
    db.commit()
    db.refresh(run)

    if inbound_channel:
        db.add(
            Message(
                run_id=run.id, sender="human", recipient="workflow", role="human",
                channel=inbound_channel, content=input_text,
            )
        )
        db.commit()

    try:
        out = await execute_spec(
            spec=spec, input_text=input_text, run_id=run.id, agent_lookup=_agent_lookup(db)
        )
        _persist_results(db, run, out)
        run.status = "completed"
        run.output = out["final"]
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.error = str(exc)
    finally:
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)
    return run


async def run_workflow(
    db: Session, workflow: Workflow, input_text: str, thread_id: str = "default"
) -> Run:
    """Execute a saved Workflow and persist all results."""
    return await run_persisted(
        db, workflow.graph_spec, input_text, thread_id, workflow_id=workflow.id
    )


def _persist_results(db: Session, run: Run, out: dict) -> None:
    for m in out["messages"]:
        db.add(
            Message(
                run_id=run.id,
                sender=m.get("sender", ""),
                recipient=m.get("recipient", ""),
                channel=m.get("channel", "internal"),
                role=m.get("role", "agent"),
                content=m.get("content", ""),
            )
        )
    for u in out["usage"]:
        db.add(
            Usage(
                run_id=run.id,
                agent=u.agent,
                model=u.model,
                prompt_tokens=u.prompt_tokens,
                completion_tokens=u.completion_tokens,
                cost_usd=u.cost_usd,
            )
        )
    db.commit()
