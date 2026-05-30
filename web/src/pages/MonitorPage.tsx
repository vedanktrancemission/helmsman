import { useEffect, useRef, useState } from "react";
import { api, openEventSocket, RunDetail } from "../lib/api";

interface LiveEvent {
  type: string;
  node?: string;
  output?: string;
  content?: string;
  sender?: string;
  recipient?: string;
  role?: string;
  tool?: string;
  observation?: string;
  total_cost_usd?: number;
  total_tokens?: number;
}

export default function MonitorPage() {
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [runs, setRuns] = useState<RunDetail[]>([]);
  const [selected, setSelected] = useState<RunDetail | null>(null);
  const [cost, setCost] = useState(0);
  const [tokens, setTokens] = useState(0);
  const [connected, setConnected] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ws = openEventSocket((e: LiveEvent) => {
      setEvents((prev) => [...prev.slice(-200), e]);
      if (typeof e.total_cost_usd === "number") setCost(e.total_cost_usd);
      if (typeof e.total_tokens === "number") setTokens(e.total_tokens);
      if (e.type === "run_end") api.listRuns().then(setRuns);
    });
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    api.listRuns().then(setRuns);
    return () => ws.close();
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [events]);

  const agentMessages = events.filter((e) => e.type === "agent_message");

  return (
    <div>
      <div className="row" style={{ marginBottom: 14 }}>
        <div className="card" style={{ flex: 1 }}>
          <div className="label">Live WebSocket</div>
          <div className="stat" style={{ color: connected ? "var(--green)" : "var(--red)" }}>
            {connected ? "● connected" : "○ disconnected"}
          </div>
        </div>
        <div className="card" style={{ flex: 1 }}>
          <div className="label">Session tokens</div>
          <div className="stat">{tokens.toLocaleString()}</div>
        </div>
        <div className="card" style={{ flex: 1 }}>
          <div className="label">Session cost (USD)</div>
          <div className="stat">${cost.toFixed(4)}</div>
        </div>
      </div>

      <div className="row">
        <div className="card" style={{ flex: 1 }}>
          <h3>Inter-agent messages (live)</h3>
          {agentMessages.length === 0 && <div className="muted">Run a workflow to see messages stream in.</div>}
          {agentMessages.map((m, i) => (
            <div key={i} className={`msg ${m.role === "tool" ? "tool" : m.sender === "human" ? "human" : ""}`}>
              <div className="who">{m.sender} → {m.recipient}</div>
              <div>{m.content}</div>
            </div>
          ))}
        </div>

        <div className="card" style={{ flex: 1 }}>
          <h3>Run log (live)</h3>
          <div ref={logRef} style={{ maxHeight: 360, overflow: "auto" }}>
            {events.map((e, i) => (
              <div className="logline" key={i}>
                <span className="muted">[{e.type}]</span>{" "}
                {e.node && <strong>{e.node}</strong>}{" "}
                {e.tool && <span>tool={e.tool} → {String(e.observation).slice(0, 50)}</span>}
                {e.type === "node_end" && <span> ✓ {String(e.output).slice(0, 60)}</span>}
                {e.type === "run_end" && <span> ✦ done · ${e.total_cost_usd?.toFixed(4)}</span>}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h3>Run history (persisted)</h3>
        <div className="row">
          <div style={{ flex: 1 }}>
            {runs.map((r) => (
              <div
                key={r.id}
                className="card"
                style={{ marginBottom: 8, cursor: "pointer", borderColor: selected?.id === r.id ? "var(--accent)" : undefined }}
                onClick={() => api.getRun(r.id).then(setSelected)}
              >
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <strong>{r.input.slice(0, 50)}</strong>
                  <span className="muted">{r.status}</span>
                </div>
              </div>
            ))}
          </div>
          <div style={{ flex: 1 }}>
            {selected ? (
              <>
                <div className="label">Persisted message history · ${selected.total_cost_usd?.toFixed(4)} · {selected.total_tokens} tok</div>
                {selected.messages.map((m) => (
                  <div key={m.id} className={`msg ${m.role === "tool" ? "tool" : m.role === "human" ? "human" : ""}`}>
                    <div className="who">{m.sender} → {m.recipient} <span className="muted">({m.channel})</span></div>
                    <div>{m.content}</div>
                  </div>
                ))}
              </>
            ) : (
              <div className="muted">Select a run to view its persisted message history.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
