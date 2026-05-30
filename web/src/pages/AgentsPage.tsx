import { useEffect, useState } from "react";
import { api, Agent } from "../lib/api";

const EMPTY: Partial<Agent> = {
  name: "",
  role: "",
  system_prompt: "",
  model: "fake",
  tools: [],
  guardrails: { max_tool_steps: 3 },
};

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [tools, setTools] = useState<{ name: string; description: string }[]>([]);
  const [draft, setDraft] = useState<Partial<Agent>>(EMPTY);
  const [editingId, setEditingId] = useState<string | null>(null);

  const load = () => api.listAgents().then(setAgents);
  useEffect(() => {
    load();
    api.tools().then(setTools);
  }, []);

  const save = async () => {
    if (!draft.name) return;
    if (editingId) await api.updateAgent(editingId, draft);
    else await api.createAgent(draft);
    setDraft(EMPTY);
    setEditingId(null);
    load();
  };

  const toggleTool = (t: string) => {
    const cur = draft.tools || [];
    setDraft({ ...draft, tools: cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t] });
  };

  return (
    <div className="row">
      <div className="card" style={{ flex: 1 }}>
        <h3>Agents</h3>
        {agents.length === 0 && <div className="muted">No agents yet. Create one →</div>}
        {agents.map((a) => (
          <div key={a.id} className="card" style={{ marginBottom: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <strong>{a.name}</strong>
              <span className="muted">{a.model}</span>
            </div>
            <div className="muted">{a.role}</div>
            <div style={{ marginTop: 6 }}>
              {(a.tools || []).map((t) => (
                <span className="tag" key={t}>
                  {t}
                </span>
              ))}
            </div>
            <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
              <button onClick={() => { setDraft(a); setEditingId(a.id); }}>Edit</button>
              <button onClick={async () => { await api.deleteAgent(a.id); load(); }}>Delete</button>
            </div>
          </div>
        ))}
      </div>

      <div className="card" style={{ flex: 1 }}>
        <h3>{editingId ? "Edit agent" : "New agent"}</h3>
        <div className="field">
          <div className="label">Name</div>
          <input value={draft.name || ""} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
        </div>
        <div className="field">
          <div className="label">Role</div>
          <input value={draft.role || ""} onChange={(e) => setDraft({ ...draft, role: e.target.value })} />
        </div>
        <div className="field">
          <div className="label">System prompt</div>
          <textarea
            rows={4}
            value={draft.system_prompt || ""}
            onChange={(e) => setDraft({ ...draft, system_prompt: e.target.value })}
          />
        </div>
        <div className="field">
          <div className="label">Model</div>
          <select value={draft.model || "fake"} onChange={(e) => setDraft({ ...draft, model: e.target.value })}>
            <option value="fake">fake (offline)</option>
            <option value="gpt-4o-mini">gpt-4o-mini</option>
            <option value="gpt-4o">gpt-4o</option>
            <option value="claude-3-5-sonnet-latest">claude-3-5-sonnet</option>
            <option value="claude-3-5-haiku-latest">claude-3-5-haiku</option>
          </select>
        </div>
        <div className="field">
          <div className="label">Tools</div>
          {tools.map((t) => (
            <label key={t.name} style={{ display: "block", fontSize: 13, marginBottom: 3 }}>
              <input
                type="checkbox"
                style={{ width: "auto", marginRight: 6 }}
                checked={(draft.tools || []).includes(t.name)}
                onChange={() => toggleTool(t.name)}
              />
              <strong>{t.name}</strong> <span className="muted">— {t.description.slice(0, 60)}</span>
            </label>
          ))}
        </div>
        <div className="field">
          <div className="label">Guardrail: max tool steps</div>
          <input
            type="number"
            value={(draft.guardrails as any)?.max_tool_steps ?? 3}
            onChange={(e) =>
              setDraft({ ...draft, guardrails: { ...(draft.guardrails || {}), max_tool_steps: +e.target.value } })
            }
          />
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="primary" onClick={save}>{editingId ? "Update" : "Create"}</button>
          {editingId && <button onClick={() => { setDraft(EMPTY); setEditingId(null); }}>Cancel</button>}
        </div>
      </div>
    </div>
  );
}
