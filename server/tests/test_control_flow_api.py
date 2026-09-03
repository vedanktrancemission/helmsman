"""Control-flow specs survive the API round-trip the canvas performs on save."""


def test_switch_example_instantiates_saves_and_runs(client):
    wf = client.post(
        "/api/workflows/from-template", json={"template_key": "example_switch"}
    ).json()
    assert wf["graph_spec"]["entry"] == "PickLane"
    kinds = {n["name"]: n.get("type", "agent") for n in wf["graph_spec"]["nodes"]}
    assert kinds["PickLane"] == "switch"

    # A canvas save re-PATCHes the whole spec; it must validate and stay intact.
    saved = client.patch(
        f"/api/workflows/{wf['id']}", json={"graph_spec": wf["graph_spec"]}
    )
    assert saved.status_code == 200, saved.text
    branch_edges = [e for e in saved.json()["graph_spec"]["edges"] if e.get("branch")]
    assert {e["branch"] for e in branch_edges} == {"billing", "tech", "default"}

    run = client.post(
        f"/api/workflows/{wf['id']}/run", json={"input": "billing question about my invoice"}
    )
    assert run.status_code == 200, run.text
    assert run.json()["status"] == "completed", run.json()["error"]

    detail = client.get(f"/api/runs/{run.json()['id']}").json()
    controls = [m for m in detail["messages"] if m["role"] == "control"]
    assert any(m["sender"] == "PickLane" and "billing" in m["recipient"] for m in controls)


def test_for_loop_example_runs_through_the_api(client):
    wf = client.post(
        "/api/workflows/from-template", json={"template_key": "example_for_loop"}
    ).json()
    run = client.post(f"/api/workflows/{wf['id']}/run", json={"input": "alpha, beta, gamma"})
    assert run.json()["status"] == "completed", run.json()["error"]

    detail = client.get(f"/api/runs/{run.json()['id']}").json()
    handlers = [m for m in detail["messages"] if m["sender"] == "Handler"]
    assert len(handlers) == 3
    assert any(m["sender"] == "EachItem" for m in detail["messages"])


def test_invalid_control_spec_is_rejected_with_422(client):
    wf = client.post("/api/workflows", json={"name": "wip", "graph_spec": {}}).json()
    bad = {
        "entry": "Gate",
        "nodes": [{"name": "Gate", "type": "if", "config": {"condition": ""}}],
        "edges": [],
    }
    res = client.patch(f"/api/workflows/{wf['id']}", json={"graph_spec": bad})
    assert res.status_code == 422
    assert "condition" in res.text


def test_unwired_loop_body_is_rejected_with_422(client):
    wf = client.post("/api/workflows", json={"name": "wip2", "graph_spec": {}}).json()
    bad = {
        "entry": "Loop",
        "nodes": [
            {"name": "Loop", "type": "for", "config": {"items": "[1,2]"}},
            {"name": "A", "agent": {"name": "A", "model": "fake"}},
        ],
        "edges": [{"source": "Loop", "branch": "exit", "target": "A"}],
    }
    res = client.patch(f"/api/workflows/{wf['id']}", json={"graph_spec": bad})
    assert res.status_code == 422
    assert "body" in res.text
