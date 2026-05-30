"""Critical path: message delivery — inbound channel message reaches the runtime
and the exchange is persisted."""
import pytest

from app.db.models import Message, Run
from app.db.session import SessionLocal
from app.orchestrator import handle_inbound


@pytest.mark.asyncio
async def test_inbound_message_drives_run_and_persists_history():
    reply = await handle_inbound("hello there", conversation_id="chat-123", channel="telegram")
    assert isinstance(reply, str) and reply

    db = SessionLocal()
    try:
        run = (
            db.query(Run).filter(Run.thread_id == "chat-123").order_by(Run.started_at.desc()).first()
        )
        assert run is not None
        msgs = db.query(Message).filter(Message.run_id == run.id).all()
        human = [m for m in msgs if m.role == "human"]
        agent = [m for m in msgs if m.role == "agent"]
        # Inbound human message persisted on the telegram channel...
        assert human and human[0].channel == "telegram"
        assert human[0].content == "hello there"
        # ...and at least one agent reply persisted.
        assert agent
    finally:
        db.close()


@pytest.mark.asyncio
async def test_events_stream_onto_bus_during_run():
    """The bus must carry run telemetry so the WebSocket monitor can fan it out."""
    import asyncio

    from app.runtime.bus import get_bus
    from app.runtime.executor import execute_spec
    from app.templates import get_template

    bus = get_bus()
    received: list[dict] = []

    async def collect():
        async for ev in bus.subscribe():
            received.append(ev)
            if ev.get("type") == "run_end":
                return

    collector = asyncio.create_task(collect())
    await asyncio.sleep(0)  # let the subscriber attach
    await execute_spec(
        spec=get_template("triage_routing")["graph_spec"],
        input_text="my app shows an error",
        run_id="bus-test",
    )
    await asyncio.wait_for(collector, timeout=5)

    types = {e["type"] for e in received}
    assert {"run_start", "node_start", "agent_message", "run_end"} <= types
