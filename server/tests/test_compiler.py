"""Critical path: workflow compilation + execution, incl. conditional edges and loops."""
import pytest

from app.runtime.callbacks import CostTracker
from app.runtime.compiler import WorkflowSpecError, compile_graph, recursion_limit, validate_spec
from app.runtime.executor import execute_spec
from app.runtime.nodes import ExecContext
from app.templates import get_template


def _ctx():
    async def noop(_):
        return None

    return ExecContext(run_id="t", cost=CostTracker(), emit=noop, record_message=noop)


def test_validate_spec_rejects_unknown_entry():
    with pytest.raises(WorkflowSpecError):
        validate_spec({"nodes": [{"name": "A", "agent": {"name": "A"}}], "entry": "Z", "edges": []})


def test_validate_spec_rejects_duplicate_names():
    spec = {
        "entry": "A",
        "nodes": [{"name": "A", "agent": {"name": "A"}}, {"name": "A", "agent": {"name": "A"}}],
        "edges": [],
    }
    with pytest.raises(WorkflowSpecError):
        validate_spec(spec)


@pytest.mark.asyncio
async def test_simple_two_node_graph_compiles_and_runs():
    spec = {
        "entry": "A",
        "nodes": [
            {"name": "A", "agent": {"name": "A", "model": "fake"}},
            {"name": "B", "agent": {"name": "B", "model": "fake"}},
        ],
        "edges": [{"source": "A", "target": "B"}, {"source": "B", "target": "END"}],
    }
    app = compile_graph(spec, _ctx(), {})
    result = await app.ainvoke({"input": "hello", "history": [], "outputs": {}, "steps": 0})
    assert "A" in result["outputs"] and "B" in result["outputs"]


@pytest.mark.asyncio
async def test_feedback_loop_fires_and_terminates():
    spec = get_template("research_write_review")["graph_spec"]
    out = await execute_spec(spec=spec, input_text="write a tweet", run_id="loop")
    writer_msgs = [m for m in out["messages"] if m["sender"] == "Writer"]
    # The reviewer requested a revision once, so the writer ran at least twice.
    assert len(writer_msgs) >= 2
    assert "APPROVE" in out["final"].upper()


@pytest.mark.asyncio
async def test_conditional_routing_selects_branch():
    spec = get_template("triage_routing")["graph_spec"]
    out = await execute_spec(spec=spec, input_text="I have a billing charge problem", run_id="route")
    senders = [m["sender"] for m in out["messages"] if m["role"] == "agent"]
    assert "BillingSpecialist" in senders
    assert "TechSpecialist" not in senders


def test_recursion_limit_default():
    assert recursion_limit({}) == 25
    assert recursion_limit({"recursion_limit": 7}) == 7
