"""Critical path: agent creation (and the rest of CRUD) through the API."""


def test_agent_crud_roundtrip(client):
    payload = {
        "name": "Researcher",
        "role": "researcher",
        "system_prompt": "Find facts.",
        "model": "fake",
        "tools": ["http_get"],
        "guardrails": {"max_tool_steps": 2},
    }
    created = client.post("/api/agents", json=payload).json()
    assert created["id"] and created["name"] == "Researcher"
    assert created["tools"] == ["http_get"]

    fetched = client.get(f"/api/agents/{created['id']}").json()
    assert fetched["system_prompt"] == "Find facts."

    updated = client.patch(f"/api/agents/{created['id']}", json={"role": "analyst"}).json()
    assert updated["role"] == "analyst"

    assert client.delete(f"/api/agents/{created['id']}").status_code == 204
    assert client.get(f"/api/agents/{created['id']}").status_code == 404


def test_tools_endpoint_lists_real_tools(client):
    names = {t["name"] for t in client.get("/api/agents/tools").json()}
    assert {"calculator", "http_get", "current_time"} <= names


def test_invalid_workflow_spec_rejected(client):
    bad = {"name": "bad", "graph_spec": {"nodes": [{"name": "A", "agent": {"name": "A"}}],
                                         "entry": "ZZZ", "edges": []}}
    assert client.post("/api/workflows", json=bad).status_code == 422
