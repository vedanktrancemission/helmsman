"""Critical path: workflow execution end-to-end through the API, with persisted
messages, usage, and cost tracking."""


def test_run_workflow_persists_messages_and_usage(client):
    wf = client.post("/api/workflows/from-template", json={"template_key": "research_write_review"}).json()
    run = client.post(f"/api/workflows/{wf['id']}/run", json={"input": "Write a launch tweet", "thread_id": "t1"}).json()
    assert run["status"] == "completed"

    detail = client.get(f"/api/runs/{run['id']}").json()
    senders = [m["sender"] for m in detail["messages"]]
    # researcher -> writer -> reviewer, with the feedback loop -> writer -> reviewer
    assert senders.count("Writer") >= 2
    assert detail["total_tokens"] > 0
    assert len(detail["usage"]) >= 1


def test_tool_executes_during_run(client):
    # Agent equipped with the calculator; "calc:" triggers a real tool call.
    agent = {"name": "Calc", "model": "fake", "tools": ["calculator"], "guardrails": {"max_tool_steps": 2}}
    spec = {
        "entry": "Calc",
        "nodes": [{"name": "Calc", "agent": agent}],
        "edges": [{"source": "Calc", "target": "END"}],
    }
    wf = client.post("/api/workflows", json={"name": "calc-wf", "graph_spec": spec}).json()
    run = client.post(f"/api/workflows/{wf['id']}/run", json={"input": "calc: 6*7"}).json()
    detail = client.get(f"/api/runs/{run['id']}").json()
    tool_msgs = [m for m in detail["messages"] if m["role"] == "tool"]
    assert tool_msgs, "expected a tool message"
    assert "42" in tool_msgs[0]["content"]


def test_templates_listed(client):
    keys = {t["key"] for t in client.get("/api/templates").json()}
    assert {"research_write_review", "triage_routing"} <= keys
