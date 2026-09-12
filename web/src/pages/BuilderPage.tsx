import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactFlow, {
  Background,
  Connection,
  Controls,
  Edge,
  MarkerType,
  Node,
  ReactFlowInstance,
  addEdge,
  useEdgesState,
  useNodesState,
} from "reactflow";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Agent, GraphSpec, NodeKind, NodeSpec, Template, Workflow, api } from "../lib/api";
import NodeInspector from "../components/NodeInspector";
import CanvasHero from "../components/CanvasHero";
import { FlowNodeData, nodeTypes } from "../components/FlowNodes";
import { CONTROL_KINDS, KINDS, LOOP_KINDS, branchesOf, isControl, kindOf } from "../lib/nodeKinds";

const END_NAMES = ["END", "__end__"];

/** Horizontal room the floating bars yield when the inspector is open. */
const INSPECTOR_GUTTER = 348;

/** Agents often emit <br> inside Markdown table cells. Raw HTML is deliberately
 *  not enabled (model output is untrusted), so fold the tags into something
 *  Markdown can express: a separator inside a table row, a hard break elsewhere. */
function normalizeMarkdown(md: string): string {
  const BR = /<br\s*\/?>/gi;
  return md
    .split("\n")
    .map((line) =>
      line.trimStart().startsWith("|")
        ? line.replace(/\s*<br\s*\/?>\s*[•·-]\s*/gi, " · ").replace(/\s*<br\s*\/?>\s*/gi, " · ")
        : line.replace(BR, "  \n")
    )
    .join("\n");
}
const isEnd = (t?: string) => !!t && END_NAMES.includes(t);

/** Plain agent-to-agent edges: dim enough to sit behind the nodes. */
const PLAIN_EDGE = "#46566e";

/** Arrowheads are SVG markers, so they take their colour here, not from CSS. */
function arrow(color: string) {
  return { type: MarkerType.ArrowClosed, color };
}

function branchEdgeStyle(branch: string, loopBack: boolean) {
  const stroke =
    branch === "true" ? "#3fb950"
    : branch === "false" ? "#f85149"
    : branch === "body" ? "#f5a623"
    // switch cases / exit: neutral, and dim enough not to outshine the nodes
    : "#5a6b82";
  return { stroke, strokeWidth: loopBack ? 2 : 1.5 };
}

function specToFlow(spec: GraphSpec): { nodes: Node<FlowNodeData>[]; edges: Edge[] } {
  const specByName = new Map((spec.nodes || []).map((n) => [n.name, n]));
  const nodes: Node<FlowNodeData>[] = (spec.nodes || []).map((n, i) => ({
    id: n.name,
    position: n.position || { x: 80 + i * 240, y: 140 },
    data: { label: n.name, role: n.agent?.role || "", spec: n },
    type: kindOf(n),
  }));

  const edges: Edge[] = [];
  (spec.edges || []).forEach((e, i) => {
    if (e.branch != null) {
      // Branch out of a control node. Unwired branches (target END) are simply
      // not drawn — the compiler treats a missing branch as ending the run.
      if (isEnd(e.target) || !e.target) return;
      const loopBack = LOOP_KINDS.includes(kindOf(specByName.get(e.source))) && e.branch === "body";
      edges.push({
        id: `b${i}-${e.source}-${e.branch}`,
        source: e.source,
        sourceHandle: e.branch,
        target: e.target,
        label: e.branch,
        animated: loopBack,
        style: branchEdgeStyle(e.branch, loopBack),
        markerEnd: arrow(branchEdgeStyle(e.branch, loopBack).stroke),
        data: { branch: e.branch },
      });
    } else if (e.conditional && e.branches) {
      Object.entries(e.branches).forEach(([key, target]) => {
        if (isEnd(target)) return;
        edges.push({
          id: `c${i}-${key}`,
          source: e.source,
          target,
          label: `${key}: ${e.condition?.slice(0, 24) || ""}`,
          animated: true,
          style: { stroke: "#f5a623", strokeWidth: 1.5 },
          markerEnd: arrow("#f5a623"),
          data: { conditional: true, key, condition: e.condition },
        });
      });
    } else if (e.target && !isEnd(e.target)) {
      edges.push({
        id: `e${i}`,
        source: e.source,
        target: e.target,
        style: { stroke: PLAIN_EDGE, strokeWidth: 1.5 },
        markerEnd: arrow(PLAIN_EDGE),
      });
    }
  });
  return { nodes, edges };
}

function flowToSpec(nodes: Node<FlowNodeData>[], edges: Edge[], base: GraphSpec): GraphSpec {
  const specNodes: NodeSpec[] = nodes.map((n) => ({
    ...(n.data.spec || ({ name: n.id } as NodeSpec)),
    name: n.id,
    position: n.position,
  }));

  // Legacy conditional edges keep their END-targeted branches, which the canvas
  // does not draw.
  const byCondSource: Record<string, any> = {};
  (base.edges || []).forEach((e) => {
    if (e.conditional && e.branches) {
      const endBranches: Record<string, string> = {};
      Object.entries(e.branches).forEach(([key, target]) => {
        if (isEnd(target)) endBranches[key] = target;
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
    if (e.data?.branch != null) {
      specEdges.push({ source: e.source, branch: e.data.branch, target: e.target });
    } else if (e.data?.conditional) {
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

  const entryStillExists = specNodes.some((n) => n.name === base.entry);
  return {
    entry: entryStillExists ? base.entry : (specNodes[0]?.name ?? ""),
    nodes: specNodes,
    edges: specEdges,
    recursion_limit: base.recursion_limit || undefined,
  };
}

export default function BuilderPage() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [current, setCurrent] = useState<Workflow | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<FlowNodeData>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [input, setInput] = useState("Write a launch tweet for our new feature");
  const [output, setOutput] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [showAddNode, setShowAddNode] = useState(false);
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const flowRef = useRef<ReactFlowInstance | null>(null);
  const paneRef = useRef<HTMLDivElement | null>(null);
  const runInputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    api.templates().then(setTemplates);
    api.listWorkflows().then(setWorkflows);
    api.listAgents().then((a) => {
      setAgents(a);
      if (a.length > 0) setSelectedAgentId(a[0].id);
    });
  }, []);

  const entry = current?.graph_spec?.entry || "";

  /** Grow the run input to fit its content, up to a scrollable ceiling. */
  useEffect(() => {
    const el = runInputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 320)}px`;
  }, [input]);

  /** Branch keys with no outgoing edge, per control node. */
  const unwiredByNode = useMemo(() => {
    const wired = new Map<string, Set<string>>();
    edges.forEach((e) => {
      if (e.data?.branch == null) return;
      if (!wired.has(e.source)) wired.set(e.source, new Set());
      wired.get(e.source)!.add(String(e.data.branch));
    });
    const out: Record<string, string[]> = {};
    nodes.forEach((n) => {
      if (!isControl(n.data.spec)) return;
      const have = wired.get(n.id) || new Set<string>();
      out[n.id] = branchesOf(n.data.spec).filter((b) => !have.has(b));
    });
    return out;
  }, [nodes, edges]);

  /** Nodes handed to ReactFlow, annotated with derived wiring state. */
  const displayNodes = useMemo(
    () =>
      nodes.map((n) =>
        unwiredByNode[n.id]
          ? { ...n, data: { ...n.data, unwired: unwiredByNode[n.id] } }
          : n
      ),
    [nodes, unwiredByNode]
  );

  const selected = nodes.filter((n) => n.selected);
  const selectedNode = selected.length === 1 ? selected[0] : null;

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
    (c: Connection) => {
      const source = nodes.find((n) => n.id === c.source);
      const branch = isControl(source?.data.spec) ? c.sourceHandle : null;
      if (branch) {
        const loopBack = LOOP_KINDS.includes(kindOf(source!.data.spec)) && branch === "body";
        setEdges((eds) =>
          addEdge(
            {
              ...c,
              label: branch,
              animated: loopBack,
              style: branchEdgeStyle(branch, loopBack),
              markerEnd: arrow(branchEdgeStyle(branch, loopBack).stroke),
              data: { branch },
            },
            // One target per branch handle: re-dragging a branch moves it.
            eds.filter((e) => !(e.source === c.source && e.data?.branch === branch))
          )
        );
        return;
      }
      setEdges((eds) =>
        addEdge(
          { ...c, style: { stroke: PLAIN_EDGE, strokeWidth: 1.5 }, markerEnd: arrow(PLAIN_EDGE) },
          eds
        )
      );
    },
    [nodes, setEdges]
  );

  const newWorkflow = async () => {
    const name = window.prompt("Workflow name:", "My Workflow");
    if (!name) return;
    try {
      const wf = await api.createWorkflow(name);
      setWorkflows(await api.listWorkflows());
      loadWorkflow(wf);
    } catch (err: any) {
      setOutput("error: " + err.message);
    }
  };

  const uniqueName = (base: string) => {
    let name = base;
    let i = 2;
    while (nodes.find((n) => n.id === name)) name = `${base}_${i++}`;
    return name;
  };

  /** Drop new nodes inside the visible pane, cascaded so they don't stack. */
  const nextPosition = () => {
    const flow = flowRef.current;
    const pane = paneRef.current;
    const cascade = (nodes.length % 6) * 36;
    if (!flow || !pane) return { x: 80 + nodes.length * 240, y: 140 };
    return flow.project({
      x: Math.max(50, pane.clientWidth * 0.16) + cascade,
      y: Math.max(50, pane.clientHeight * 0.2) + cascade,
    });
  };

  const placeNode = (node: Node<FlowNodeData>) => {
    setNodes((ns) => [...ns, node]);
    setShowAddNode(false);
    if (!entry && current) {
      setCurrent({ ...current, graph_spec: { ...current.graph_spec, entry: node.id } });
    }
  };

  const addAgentNode = () => {
    const agent = agents.find((a) => a.id === selectedAgentId);
    if (!agent) return;
    const name = uniqueName(agent.name);
    placeNode({
      id: name,
      position: nextPosition(),
      data: { label: name, role: agent.role, spec: { name, agent_id: agent.id } },
      type: "agent",
    });
  };

  const addControlNode = (kind: NodeKind) => {
    const name = uniqueName(KINDS[kind].label.replace(/[^A-Za-z]/g, "") || kind);
    placeNode({
      id: name,
      position: nextPosition(),
      data: { label: name, spec: { name, type: kind, config: KINDS[kind].defaults() } },
      type: kind,
    });
  };

  /** Patch a node's spec and drop edges whose branch no longer exists. */
  const updateSelectedSpec = (patch: Partial<NodeSpec>) => {
    if (!selectedNode) return;
    const id = selectedNode.id;
    let nextSpec: NodeSpec | null = null;
    setNodes((ns) =>
      ns.map((n) => {
        if (n.id !== id) return n;
        nextSpec = { ...n.data.spec, ...patch } as NodeSpec;
        return { ...n, data: { ...n.data, spec: nextSpec } };
      })
    );
    if (nextSpec) {
      const valid = new Set(branchesOf(nextSpec));
      setEdges((es) =>
        es.filter((e) => e.source !== id || e.data?.branch == null || valid.has(String(e.data.branch)))
      );
    }
  };

  const deleteSelectedNode = () => {
    const toDelete = new Set(selected.map((n) => n.id));
    if (toDelete.size === 0) return;
    setNodes((ns) => ns.filter((n) => !toDelete.has(n.id)));
    setEdges((es) => es.filter((e) => !toDelete.has(e.source) && !toDelete.has(e.target)));
    if (current && toDelete.has(entry)) {
      setCurrent({ ...current, graph_spec: { ...current.graph_spec, entry: "" } });
    }
  };

  const save = async () => {
    if (!current) return null;
    const spec = flowToSpec(nodes, edges, current.graph_spec);
    const wf = await api.updateWorkflow(current.id, { graph_spec: spec });
    setCurrent(wf);
    setWorkflows(await api.listWorkflows());
    return wf;
  };

  const saveClicked = async () => {
    try {
      await save();
      setOutput("");
    } catch (err: any) {
      setOutput("could not save: " + err.message);
    }
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

  const inspectorOpen = selectedNode !== null;
  const gutter = inspectorOpen ? { right: INSPECTOR_GUTTER } : undefined;

  return (
    <div className="builder-page" ref={paneRef}>
      <ReactFlow
        nodes={displayNodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onInit={(instance) => (flowRef.current = instance)}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        fitView
      >
        <Background color="#2a3646" gap={18} size={1} />
        <Controls position="bottom-left" />
      </ReactFlow>

      {nodes.length === 0 && (
        <div className="canvas-empty">
          <div className="canvas-empty-3d">
            <CanvasHero />
          </div>
          <div className="canvas-empty-copy">
            <h2>{current ? current.name : "Nothing loaded"}</h2>
            <p className="muted">
              {current
                ? "Add an agent or a control-flow node to start wiring this graph."
                : "Start from a template, or pick an existing workflow above."}
            </p>
          </div>
        </div>
      )}

      <div className="float-bar top" style={gutter}>
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
            style={{ width: 240 }}
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
          <button onClick={newWorkflow}>New Workflow</button>
          <button onClick={saveClicked} disabled={!current}>Save</button>
          <button
            onClick={async () => {
              if (!current || !window.confirm(`Delete workflow "${current.name}"?`)) return;
              await api.deleteWorkflow(current.id);
              setCurrent(null);
              setNodes([]);
              setEdges([]);
              setOutput("");
              setWorkflows(await api.listWorkflows());
            }}
            disabled={!current}
            style={{ color: "var(--red)", borderColor: "var(--red)" }}
          >
            Delete
          </button>
          <button onClick={() => setShowAddNode((v) => !v)} disabled={!current}>
            {showAddNode ? "Cancel" : "+ Add Node"}
          </button>
          <button
            onClick={deleteSelectedNode}
            disabled={selected.length === 0}
            style={{ color: "var(--red)", borderColor: "var(--red)" }}
          >
            Delete Node
          </button>
          <span className="label" style={{ margin: "0 0 0 16px" }}>Entry:</span>
          <select
            value={entry}
            style={{ width: 160 }}
            disabled={!current || nodes.length === 0}
            onChange={(e) =>
              current &&
              setCurrent({ ...current, graph_spec: { ...current.graph_spec, entry: e.target.value } })
            }
          >
            <option value="">— none —</option>
            {nodes.map((n) => (
              <option key={n.id} value={n.id}>{n.id}</option>
            ))}
          </select>
        </div>

        {showAddNode && (
          <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 10, flexWrap: "wrap" }}>
            <span className="label" style={{ margin: 0 }}>Agent:</span>
            {agents.length === 0 ? (
              <span className="muted">No agents — create one in the Agents tab first</span>
            ) : (
              <>
                <select
                  value={selectedAgentId}
                  style={{ width: 200 }}
                  onChange={(e) => setSelectedAgentId(e.target.value)}
                >
                  {agents.map((a) => (
                    <option key={a.id} value={a.id}>{a.name} ({a.role || "no role"})</option>
                  ))}
                </select>
                <button className="primary" onClick={addAgentNode}>Add agent</button>
              </>
            )}
            <span className="label" style={{ margin: "0 0 0 16px" }}>Control flow:</span>
            {CONTROL_KINDS.map((kind) => {
              const { Icon } = KINDS[kind];
              return (
                <button
                  key={kind}
                  className="btn-icon"
                  onClick={() => addControlNode(kind)}
                  title={KINDS[kind].hint}
                >
                  <Icon size={13} strokeWidth={2.2} /> {KINDS[kind].label}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {selectedNode && (
        <div className="float-panel inspector">
          <NodeInspector
            spec={selectedNode.data.spec}
            unwired={unwiredByNode[selectedNode.id] || []}
            onChange={updateSelectedSpec}
          />
        </div>
      )}

      <div className="float-bar bottom" style={gutter}>
        <div className="label">Run input</div>
        <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
          <textarea
            ref={runInputRef}
            className="run-input"
            value={input}
            rows={1}
            spellCheck={false}
            placeholder="e.g.  - 2x Big Mac (no pickles on one)"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              // Enter and Shift+Enter both add a line; Cmd/Ctrl+Enter runs, so a
              // half-typed multi-line order can never fire a paid model call.
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                if (current && !busy) run();
              }
            }}
          />
          <button className="primary" onClick={run} disabled={!current || busy}>Run ▶</button>
        </div>
        <div className="muted" style={{ marginTop: 6 }}>
          One line per item · Enter adds a line ·{" "}
          {navigator.platform.startsWith("Mac") ? "⌘" : "Ctrl+"}Enter runs
        </div>
        {output && (
          <div className="card run-output" style={{ marginTop: 10 }}>
            <div className="label">Output</div>
            <div className="chat-markdown md-output">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{normalizeMarkdown(output)}</ReactMarkdown>
            </div>
            <div className="muted" style={{ marginTop: 6 }}>
              See the Monitor tab for live inter-agent messages, branch decisions, and cost.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
