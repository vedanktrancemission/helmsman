import { useState } from "react";
import { NodeConfig, NodeSpec } from "../lib/api";
import { EXPRESSION_VARS, KINDS, branchesOf, kindOf } from "../lib/nodeKinds";

interface Props {
  spec: NodeSpec;
  /** Branch keys that currently have no outgoing edge. */
  unwired: string[];
  onChange: (patch: Partial<NodeSpec>) => void;
}

function ExprField({
  label, help, value, onChange, rows = 2,
}: { label: string; help: string; value: string; onChange: (v: string) => void; rows?: number }) {
  return (
    <div className="field">
      <div className="label">{label}</div>
      <textarea
        rows={rows}
        value={value}
        spellCheck={false}
        style={{ fontFamily: "ui-monospace, monospace", resize: "vertical" }}
        onChange={(e) => onChange(e.target.value)}
      />
      <div className="muted">{help}</div>
    </div>
  );
}

export default function NodeInspector({ spec, unwired, onChange }: Props) {
  const [showVars, setShowVars] = useState(false);
  const kind = kindOf(spec);
  const info = KINDS[kind];
  const cfg: NodeConfig = spec.config || {};
  const setCfg = (patch: NodeConfig) => onChange({ config: { ...cfg, ...patch } });

  if (kind === "agent") {
    return (
      <div>
        <div className="label">Selected node</div>
        <div style={{ fontWeight: 600, marginBottom: 6 }}>◆ {spec.name}</div>
        <div className="muted">
          Agent node — edit its prompt, model, and tools in the Agents tab.
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="label">Selected node</div>
      <div style={{ fontWeight: 600, marginBottom: 2 }}>
        {info.icon} {spec.name} <span className="muted">· {info.label}</span>
      </div>
      <div className="muted" style={{ marginBottom: 10 }}>{info.hint}</div>

      {(kind === "if" || kind === "while") && (
        <ExprField
          label="Condition"
          help={
            kind === "if"
              ? "Python expression. Truthy takes the true branch."
              : "Re-evaluated before every body pass; false exits the loop."
          }
          value={cfg.condition || ""}
          onChange={(v) => setCfg({ condition: v })}
        />
      )}

      {kind === "switch" && (
        <>
          <ExprField
            label="Expression"
            help="Its value is matched against the cases below (compared as text)."
            value={cfg.expression || ""}
            onChange={(v) => setCfg({ expression: v })}
          />
          <div className="field">
            <div className="label">Cases (comma separated)</div>
            <input
              value={(cfg.cases || []).join(", ")}
              spellCheck={false}
              onChange={(e) =>
                setCfg({
                  cases: e.target.value
                    .split(",")
                    .map((c) => c.trim())
                    .filter((c) => c && c !== "default"),
                })
              }
            />
            <div className="muted">
              Each case gets its own handle; unmatched values fall to <code>default</code>.
            </div>
          </div>
        </>
      )}

      {kind === "for" && (
        <ExprField
          label="Items"
          help="Expression producing the collection. A string splits on newlines; an int becomes a range."
          value={cfg.items || ""}
          onChange={(v) => setCfg({ items: v })}
        />
      )}

      {(kind === "for" || kind === "while") && (
        <div className="field">
          <div className="label">Max iterations</div>
          <input
            type="number"
            min={1}
            value={cfg.max_iterations ?? 10}
            onChange={(e) => setCfg({ max_iterations: Math.max(1, Number(e.target.value) || 1) })}
          />
          <div className="muted">Hard guard — the loop exits here even if the condition holds.</div>
        </div>
      )}

      <div className="field">
        <div className="label">Branches</div>
        {branchesOf(spec).map((b) => (
          <span key={b} className="tag">
            {b}
            {unwired.includes(b) ? " — ends run" : ""}
          </span>
        ))}
        <div className="muted" style={{ marginTop: 4 }}>
          Drag from a branch handle to wire it. A loop's <code>body</code> must lead back to this
          node.
        </div>
      </div>

      <button onClick={() => setShowVars((v) => !v)}>
        {showVars ? "Hide" : "Show"} available variables
      </button>
      {showVars && (
        <div style={{ marginTop: 8 }}>
          {EXPRESSION_VARS.map(([name, desc]) => (
            <div key={name} className="muted" style={{ padding: "2px 0" }}>
              <code>{name}</code> — {desc}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
