import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { api, Agent } from "../lib/api";

const CHANNELS = ["telegram"];

/** Agents per page in the list column. */
const PAGE_SIZE = 6;

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
  const [page, setPage] = useState(0);

  const load = () =>
    api.listAgents().then((list) => {
      setAgents(list);
      return list;
    });
  useEffect(() => {
    load();
    api.tools().then(setTools);
  }, []);

  const save = async () => {
    if (!draft.name) return;
    const skills = skillsText.split(",").map((s) => s.trim()).filter(Boolean);
    const payload = { ...draft, skills };
    const saved = editingId
      ? await api.updateAgent(editingId, payload)
      : await api.createAgent(payload);
    setDraft(EMPTY);
    setSkillsText("");
    setEditingId(null);
    // Jump to whichever page now holds it, so a new agent is never created
    // onto a page the user cannot see.
    const list = await load();
    const i = list.findIndex((a) => a.id === saved.id);
    if (i >= 0) setPage(Math.floor(i / PAGE_SIZE));
  };

  const remove = async (id: string) => {
    await api.deleteAgent(id);
    // Deleting the agent currently loaded in the form would otherwise leave it
    // in edit mode pointing at a row that no longer exists.
    if (editingId === id) {
      setDraft(EMPTY);
      setSkillsText("");
      setEditingId(null);
    }
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

  const pageCount = Math.max(1, Math.ceil(agents.length / PAGE_SIZE));
  // Derived rather than stored, so deleting the last row of the last page can
  // never strand the view on an empty page.
  const current = Math.min(page, pageCount - 1);
  const visible = agents.slice(current * PAGE_SIZE, current * PAGE_SIZE + PAGE_SIZE);

  return (
    <div className="row">
      <div className="card" style={{ flex: 1 }}>
        <div className="list-head">
          <h3>Agents</h3>
          {agents.length > 0 && (
            <span className="muted">
              {agents.length} total
              {pageCount > 1 && ` · showing ${current * PAGE_SIZE + 1}\u2013${current * PAGE_SIZE + visible.length}`}
            </span>
          )}
        </div>
        {agents.length === 0 && <div className="muted">No agents yet. Create one →</div>}
        {visible.map((a) => (
          <div key={a.id} className="card" style={{ marginBottom: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <strong>{a.name}</strong>
              <span className="muted">{a.model}</span>
            </div>
            <div className="muted">{a.role}</div>
            <div style={{ marginTop: 6 }}>
              {(a.tools || []).map((t) => <span className="tag" key={t}>{t}</span>)}
              {(a.channels || []).map((c) => <span className="tag accent" key={c}>{c}</span>)}
              {(a.skills || []).map((s) => <span className="tag dim" key={s}>{s}</span>)}
            </div>
            <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
              <button onClick={() => { setDraft(a); setSkillsText((a.skills || []).join(", ")); setEditingId(a.id); }}>Edit</button>
              <button onClick={() => remove(a.id)}>Delete</button>
            </div>
          </div>
        ))}

        {pageCount > 1 && (
          <div className="pager">
            <button
              className="btn-icon"
              onClick={() => setPage(current - 1)}
              disabled={current === 0}
            >
              <ChevronLeft size={14} strokeWidth={2.2} /> Prev
            </button>
            <span className="muted">
              Page {current + 1} of {pageCount}
            </span>
            <button
              className="btn-icon"
              onClick={() => setPage(current + 1)}
              disabled={current >= pageCount - 1}
            >
              Next <ChevronRight size={14} strokeWidth={2.2} />
            </button>
          </div>
        )}
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
            <optgroup label="OpenRouter (free)">
              <option value="nvidia/nemotron-3-ultra-550b-a55b:free">Nemotron 3 Ultra — 1M ctx</option>
              <option value="nvidia/nemotron-3.5-lightning:free">Nemotron 3.5 Lightning — 1M ctx</option>
              <option value="nvidia/nemotron-3-super-120b-a12b:free">Nemotron 3 Super — 262K ctx</option>
              <option value="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free">Nemotron 3 Nano Omni — 256K ctx</option>
              <option value="poolside/laguna-s-2.1:free">Laguna S 2.1 — 262K ctx</option>
              <option value="poolside/laguna-xs-2.1:free">Laguna XS 2.1 — 262K ctx</option>
              <option value="dots-studio/dots-3-note-preview:free">Dots3-Note Preview — 512K ctx</option>
              <option value="nex-agi/nex-n2.5-pro:free">Nex-N2.5-Pro — 262K ctx</option>
              <option value="nex-agi/nex-n2.5-mini:free">Nex-N2.5-Mini — 262K ctx</option>
              <option value="cohere/north-mini-code:free">North Mini Code — 256K ctx</option>
              <option value="google/gemma-4-31b-it:free">Gemma 4 31B — 262K ctx</option>
              <option value="google/gemma-4-26b-a4b-it:free">Gemma 4 26B A4B — 262K ctx</option>
              <option value="inclusionai/ling-3.0-flash-fin:free">Ling 3.0 Flash Fin — 262K ctx</option>
              <option value="inclusionai/ling-3.0-flash-sante:free">Ling 3.0 Flash Sante — 262K ctx</option>
              <option value="liquid/lfm-2.5-2.6b:free">LFM2.5-2.6B — 66K ctx</option>
            </optgroup>
            <optgroup label="Groq">
              <option value="groq:openai/gpt-oss-120b">gpt-oss-120b</option>
              <option value="groq:openai/gpt-oss-20b">gpt-oss-20b</option>
              <option value="groq:qwen/qwen3.8-27b">qwen3.8-27b</option>
              <option value="groq:groq/compound-mini">compound-mini</option>
            </optgroup>
            <optgroup label="Gemini">
              <option value="gemini-3.5-flash-lite">gemini-3.5-flash-lite (fastest)</option>
              <option value="gemini-3.7-flash">gemini-3.7-flash</option>
              <option value="gemini-flash-lite-latest">gemini-flash-lite-latest</option>
              <option value="gemini-flash-latest">gemini-flash-latest</option>
            </optgroup>
            <optgroup label="Mistral">
              <option value="mistral-small-latest">mistral-small-latest</option>
              <option value="mistral-medium-latest">mistral-medium-latest</option>
            </optgroup>
            <optgroup label="OpenAI">
              <option value="gpt-4o">gpt-4o</option>
              <option value="gpt-4o-mini">gpt-4o-mini</option>
            </optgroup>
            <optgroup label="Anthropic">
              <option value="claude-opus-5">claude-opus-5</option>
              <option value="claude-sonnet-5">claude-sonnet-5</option>
              <option value="claude-haiku-4-5">claude-haiku-4.5</option>
            </optgroup>
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
