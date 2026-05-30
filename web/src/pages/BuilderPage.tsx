import { useCallback, useEffect, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  Connection,
  Edge,
  Node,
  addEdge,
  useEdgesState,
  useNodesState,
  MarkerType,
} from "reactflow";
import { api, GraphSpec, Template, Workflow } from "../lib/api";

function specToFlow(spec: GraphSpec): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = (spec.nodes || []).map((n, i) => ({
    id: n.name,
    position: n.position || { x: 80 + i * 220, y: 140 },
    data: { label: n.name, role: n.agent?.role || "", spec: n },
    type: "default",
  }));
  const edges: Edge[] = [];
  (spec.edges || []).forEach((e, i) => {
    if (e.conditional && e.branches) {
      Object.entries(e.branches).forEach(([key, target]) => {
        if (target === "END" || target === "__end__") return;
        edges.push({
          id: `c${i}-${key}`,
          source: e.source,
          target,
          label: `${key}: ${e.condition?.slice(0, 24) || ""}`,
          animated: true,
          style: { stroke: "#f5a623" },
          markerEnd: { type: MarkerType.ArrowClosed },
          data: { conditional: true, key, condition: e.condition },
        });
      });
    } else if (e.target && e.target !== "END" && e.target !== "__end__") {
      edges.push({
        id: `e${i}`,
        source: e.source,
        target: e.target,
        markerEnd: { type: MarkerType.ArrowClosed },
      });
    }
  });
  return { nodes, edges };
}

function flowToSpec(nodes: Node[], edges: Edge[], base: GraphSpec): GraphSpec {
  const specNodes = nodes.map((n) => ({
    ...(n.data.spec || {}),
    name: n.id,
    position: n.position,
  }));

  const byCondSource: Record<string, any> = {};
  (base.edges || []).forEach((e) => {
    if (e.conditional && e.branches) {
      const endBranches: Record<string, string> = {};
      Object.entries(e.branches).forEach(([key, target]) => {
        if (target === "END" || target === "__end__") endBranches[key] = target;
      });
      if (Object.keys(endBranches).length > 0) {
        byCondSource[e.source] = {
          source: e.source,
          conditional: true,
          condition: e.condition,
          branches: { ...endBranches },
        };
      }
    }
  });

  const specEdges: any[] = [];
  edges.forEach((e) => {
    if (e.data?.conditional) {
      const src = (byCondSource[e.source] ||= {
        source: e.source,
        conditional: true,
        condition: e.data.condition,
        branches: {},
      });
      src.branches[e.data.key] = e.target;
    } else {
      specEdges.push({ source: e.source, target: e.target });
    }
  });
  Object.values(byCondSource).forEach((c) => specEdges.push(c));
  return {
    entry: base.entry || (specNodes[0]?.name ?? ""),
    nodes: specNodes,
    edges: specEdges,
    recursion_limit: base.recursion_limit || 25,
  };
}

export default function BuilderPage() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [current, setCurrent] = useState<Workflow | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [input, setInput] = useState("Write a launch tweet for our new feature");
  const [output, setOutput] = useState<string>("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.templates().then(setTemplates);
    api.listWorkflows().then(setWorkflows);
  }, []);

  const loadWorkflow = (wf: Workflow) => {
    setCurrent(wf);
    const { nodes: n, edges: e } = specToFlow(wf.graph_spec);
    setNodes(n);
    setEdges(e);
    setOutput("");
  };

  const instantiate = async (key: string) => {
    const wf = await api.fromTemplate(key);
    setWorkflows(await api.listWorkflows());
    loadWorkflow(wf);
  };

  const onConnect = useCallback(
    (c: Connection) => setEdges((eds) => addEdge({ ...c, markerEnd: { type: MarkerType.ArrowClosed } }, eds)),
    [setEdges]
  );

  const save = async () => {
    if (!current) return;
    const spec = flowToSpec(nodes, edges, current.graph_spec);
    const wf = await api.updateWorkflow(current.id, { graph_spec: spec });
    setCurrent(wf);
    setWorkflows(await api.listWorkflows());
  };

  const run = async () => {
    if (!current) return;
    setBusy(true);
    setOutput("running…");
    try {
      await save();
      const res = await api.runWorkflow(current.id, input);
      setOutput(res.output || res.error || "(no output)");
    } catch (err: any) {
      setOutput("error: " + err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="card" style={{ marginBottom: 14 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <span className="label" style={{ margin: 0 }}>Templates:</span>
          {templates.map((t) => (
            <button key={t.key} onClick={() => instantiate(t.key)} title={t.description}>
              + {t.name}
            </button>
          ))}
          <span className="label" style={{ margin: "0 0 0 16px" }}>Workflows:</span>
          <select
            value={current?.id || ""}
            style={{ width: 260 }}
            onChange={(e) => {
              const wf = workflows.find((w) => w.id === e.target.value);
              if (wf) loadWorkflow(wf);
            }}
          >
            <option value="">— select —</option>
            {workflows.map((w) => (
              <option key={w.id} value={w.id}>{w.name}</option>
            ))}
          </select>
          <button onClick={save} disabled={!current}>Save</button>
        </div>
      </div>

      <div className="builder">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          fitView
        >
          <Background color="#2c3947" />
          <Controls />
        </ReactFlow>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <div className="label">Run input</div>
        <div style={{ display: "flex", gap: 10 }}>
          <input value={input} onChange={(e) => setInput(e.target.value)} />
          <button className="primary" onClick={run} disabled={!current || busy}>Run ▶</button>
        </div>
        {output && (
          <div className="card" style={{ marginTop: 10, whiteSpace: "pre-wrap" }}>
            <div className="label">Output</div>
            {output}
            <div className="muted" style={{ marginTop: 6 }}>
              See the Monitor tab for live inter-agent messages, logs, and cost.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
