import { useEffect, useState } from "react";
import { api, Agent } from "../lib/api";

const CHANNELS = ["telegram"];

const EMPTY: Partial<Agent> = {
  name: "",
  role: "",
  system_prompt: "",
  model: "fake",
  tools: [],
  channels: [],
  schedule: {},
  memory_config: { type: "none" },
  skills: [],
  guardrails: { max_tool_steps: 3 },
};

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [tools, setTools] = useState<{ name: string; description: string }[]>([]);
  const [draft, setDraft] = useState<Partial<Agent>>(EMPTY);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [skillsText, setSkillsText] = useState("");

  const load = () => api.listAgents().then(setAgents);
  useEffect(() => {
    load();
    api.tools().then(setTools);
  }, []);

  const save = async () => {
    if (!draft.name) return;
    const skills = skillsText.split(",").map((s) => s.trim()).filter(Boolean);
    const payload = { ...draft, skills };
    if (editingId) await api.updateAgent(editingId, payload);
    else await api.createAgent(payload);
    setDraft(EMPTY);
    setSkillsText("");
    setEditingId(null);
    load();
  };

  const toggleTool = (t: string) => {
    const cur = draft.tools || [];
    setDraft({ ...draft, tools: cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t] });
  };

  const toggleChannel = (c: string) => {
    const cur = draft.channels || [];
    setDraft({ ...draft, channels: cur.includes(c) ? cur.filter((x) => x !== c) : [...cur, c] });
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
              {(a.tools || []).map((t) => <span className="tag" key={t}>{t}</span>)}
              {(a.channels || []).map((c) => <span className="tag" key={c} style={{ background: "var(--accent)" }}>{c}</span>)}
              {(a.skills || []).map((s) => <span className="tag" key={s} style={{ opacity: 0.7 }}>{s}</span>)}
            </div>
            <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
              <button onClick={() => { setDraft(a); setSkillsText((a.skills || []).join(", ")); setEditingId(a.id); }}>Edit</button>
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
            <option value="google/gemma-4-31b-it:free">google/gemma-4-31b-it:free (OpenRouter)</option>
            <option value="google/gemma-4-26b-a4b-it:free">google/gemma-4-26b-a4b-it:free (OpenRouter)</option>
            <option value="moonshotai/kimi-k2.6:free">moonshotai/kimi-k2.6:free (OpenRouter)</option>
            <option value="nvidia/nemotron-3-super-120b-a12b:free">nvidia/nemotron-3-super-120b-a12b:free (OpenRouter)</option>
            <option value="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free">nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free (OpenRouter)</option>
            <option value="gemini-2.0-flash">gemini-2.0-flash (Gemini)</option>
            <option value="gemini-2.5-flash-preview-05-20">gemini-2.5-flash (Gemini)</option>
            <option value="gemini-2.5-pro-preview-06-05">gemini-2.5-pro (Gemini)</option>
            <option value="mistral-small-latest">mistral-small-latest (Mistral)</option>
            <option value="mistral-medium-latest">mistral-medium-latest (Mistral)</option>
            <option value="open-mistral-7b">open-mistral-7b (Mistral)</option>
            <option value="gpt-4o-mini">gpt-4o-mini (OpenAI)</option>
            <option value="gpt-4o">gpt-4o (OpenAI)</option>
            <option value="claude-3-5-sonnet-latest">claude-3-5-sonnet (Anthropic)</option>
            <option value="claude-3-5-haiku-latest">claude-3-5-haiku (Anthropic)</option>
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
          <div className="label">Channels</div>
          {CHANNELS.map((c) => (
            <label key={c} style={{ display: "block", fontSize: 13, marginBottom: 3 }}>
              <input
                type="checkbox"
                style={{ width: "auto", marginRight: 6 }}
                checked={(draft.channels || []).includes(c)}
                onChange={() => toggleChannel(c)}
              />
              {c}
            </label>
          ))}
        </div>
        <div className="field">
          <div className="label">Schedule (cron)</div>
          <input
            placeholder="e.g. 0 9 * * * (daily at 9am)"
            value={(draft.schedule as any)?.cron || ""}
            onChange={(e) => setDraft({ ...draft, schedule: { cron: e.target.value } })}
          />
        </div>
        <div className="field">
          <div className="label">Schedule: prompt</div>
          <input
            placeholder="e.g. Send the daily briefing"
            value={(draft.schedule as any)?.prompt || ""}
            onChange={(e) => setDraft({ ...draft, schedule: { ...(draft.schedule || {}), prompt: e.target.value } })}
          />
        </div>
        <div className="field">
          <div className="label">Memory</div>
          <select
            value={(draft.memory_config as any)?.type || "none"}
            onChange={(e) => setDraft({ ...draft, memory_config: { type: e.target.value } })}
          >
            <option value="none">None</option>
            <option value="conversation">Conversation (last N turns)</option>
            <option value="semantic">Semantic (vector search)</option>
          </select>
        </div>
        <div className="field">
          <div className="label">Interaction rules</div>
          <textarea
            rows={2}
            placeholder="Custom instructions appended to the system prompt (e.g. always reply in bullet points)"
            value={(draft.interaction_rules as any)?.instructions || ""}
            onChange={(e) =>
              setDraft({ ...draft, interaction_rules: { ...(draft.interaction_rules || {}), instructions: e.target.value } })
            }
          />
        </div>
        <div className="field">
          <div className="label">Skills (comma-separated)</div>
          <input
            placeholder="e.g. summarisation, translation"
            value={skillsText}
            onChange={(e) => setSkillsText(e.target.value)}
          />
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
        <div className="field">
          <div className="label">Guardrail: max output chars <span className="muted">(0 = unlimited)</span></div>
          <input
            type="number"
            value={(draft.guardrails as any)?.max_output_chars ?? 0}
            onChange={(e) =>
              setDraft({ ...draft, guardrails: { ...(draft.guardrails || {}), max_output_chars: +e.target.value } })
            }
          />
        </div>
        <div className="field">
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer" }}>
            <input
              type="checkbox"
              style={{ width: "auto" }}
              checked={!!(draft.guardrails as any)?.restrict_to_role}
              onChange={(e) =>
                setDraft({ ...draft, guardrails: { ...(draft.guardrails || {}), restrict_to_role: e.target.checked } })
              }
            />
            <span>Restrict to role domain</span>
            <span className="muted">— refuse off-topic queries</span>
          </label>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="primary" onClick={save}>{editingId ? "Update" : "Create"}</button>
          {editingId && <button onClick={() => { setDraft(EMPTY); setSkillsText(""); setEditingId(null); }}>Cancel</button>}
        </div>
      </div>
    </div>
  );
}
