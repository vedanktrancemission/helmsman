import { memo } from "react";
import { Handle, NodeProps, Position } from "reactflow";
import { NodeSpec } from "../lib/api";
import { KINDS, branchesOf, kindOf } from "../lib/nodeKinds";

export interface FlowNodeData {
  label: string;
  role?: string;
  spec: NodeSpec;
  /** Branch keys with no outgoing edge — those end the run. */
  unwired?: string[];
}

const BRANCH_TONE: Record<string, string> = {
  true: "var(--green)",
  false: "var(--red)",
  body: "var(--accent)",
  exit: "var(--muted)",
  default: "var(--muted)",
};

function tone(branch: string): string {
  return BRANCH_TONE[branch] || "var(--accent-2)";
}

/** One labelled source handle, positioned against its own row. */
function BranchRow({ branch, unwired }: { branch: string; unwired: boolean }) {
  return (
    <div className="branch-row" title={unwired ? `${branch} is unwired — it ends the run` : branch}>
      <span className="branch-name" style={{ color: tone(branch) }}>
        {branch}
        {unwired && <span className="branch-open"> ⊘</span>}
      </span>
      <Handle
        type="source"
        id={branch}
        position={Position.Right}
        className="branch-handle"
        style={{ background: tone(branch) }}
      />
    </div>
  );
}

function ControlNode({ data, selected }: NodeProps<FlowNodeData>) {
  const kind = kindOf(data.spec);
  const info = KINDS[kind];
  const cfg = data.spec.config || {};
  const branches = branchesOf(data.spec);
  const unwired = new Set(data.unwired || []);
  const expr = cfg.condition || cfg.expression || cfg.items || "";

  return (
    <div className={`node-card control ${kind} ${selected ? "selected" : ""}`}>
      <Handle type="target" position={Position.Left} />
      <div className="node-head">
        <span className="node-icon">{info.icon}</span>
        <span className="node-title">{data.label}</span>
        <span className="node-kind">{info.label}</span>
      </div>
      <div className="node-expr" title={expr}>
        {expr || <span className="muted">no expression set</span>}
      </div>
      {cfg.max_iterations != null && (
        <div className="node-meta">max {cfg.max_iterations} iterations</div>
      )}
      <div className="branch-list">
        {branches.map((b) => (
          <BranchRow key={b} branch={b} unwired={unwired.has(b)} />
        ))}
      </div>
    </div>
  );
}

function AgentNode({ data, selected }: NodeProps<FlowNodeData>) {
  return (
    <div className={`node-card agent ${selected ? "selected" : ""}`}>
      <Handle type="target" position={Position.Left} />
      <div className="node-head">
        <span className="node-icon">◆</span>
        <span className="node-title">{data.label}</span>
      </div>
      {data.role && <div className="role">{data.role}</div>}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

/** Registered once and passed to ReactFlow by identity — never rebuild inline. */
export const nodeTypes = {
  agent: memo(AgentNode),
  if: memo(ControlNode),
  switch: memo(ControlNode),
  while: memo(ControlNode),
  for: memo(ControlNode),
};
