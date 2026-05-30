const API_BASE: string =
  (import.meta as any).env?.VITE_API_BASE || "http://localhost:8000";
const WS_BASE = API_BASE.replace(/^http/, "ws");

export interface Agent {
  id: string;
  name: string;
  role: string;
  system_prompt: string;
  model: string;
  tools: string[];
  channels: string[];
  schedule: Record<string, any>;
  memory_config: Record<string, any>;
  skills: string[];
  interaction_rules: Record<string, any>;
  guardrails: Record<string, any>;
}

export interface NodeSpec {
  name: string;
  agent_id?: string;
  agent?: Partial<Agent>;
  position?: { x: number; y: number };
}
export interface EdgeSpec {
  source: string;
  target?: string;
  conditional?: boolean;
  condition?: string;
  branches?: Record<string, string>;
}
export interface GraphSpec {
  entry: string;
  nodes: NodeSpec[];
  edges: EdgeSpec[];
  recursion_limit?: number;
}
export interface Workflow {
  id: string;
  name: string;
  description: string;
  graph_spec: GraphSpec;
  template_source: string;
}
export interface Message {
  id: string;
  run_id: string | null;
  sender: string;
  recipient: string;
  channel: string;
  role: string;
  content: string;
  created_at: string;
}
export interface RunDetail {
  id: string;
  status: string;
  input: string;
  output: string;
  error: string;
  messages: Message[];
  usage: any[];
  total_cost_usd: number;
  total_tokens: number;
}
export interface Template {
  key: string;
  name: string;
  description: string;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const api = {
  listAgents: () => req<Agent[]>("/api/agents"),
  tools: () => req<{ name: string; description: string }[]>("/api/agents/tools"),
  createAgent: (a: Partial<Agent>) =>
    req<Agent>("/api/agents", { method: "POST", body: JSON.stringify(a) }),
  updateAgent: (id: string, a: Partial<Agent>) =>
    req<Agent>(`/api/agents/${id}`, { method: "PATCH", body: JSON.stringify(a) }),
  deleteAgent: (id: string) => req<void>(`/api/agents/${id}`, { method: "DELETE" }),

  listWorkflows: () => req<Workflow[]>("/api/workflows"),
  updateWorkflow: (id: string, w: Partial<Workflow>) =>
    req<Workflow>(`/api/workflows/${id}`, { method: "PATCH", body: JSON.stringify(w) }),
  fromTemplate: (template_key: string, name?: string) =>
    req<Workflow>("/api/workflows/from-template", {
      method: "POST",
      body: JSON.stringify({ template_key, name }),
    }),
  runWorkflow: (id: string, input: string, thread_id = "ui") =>
    req<RunDetail>(`/api/workflows/${id}/run`, {
      method: "POST",
      body: JSON.stringify({ input, thread_id }),
    }),

  listRuns: () => req<RunDetail[]>("/api/runs"),
  getRun: (id: string) => req<RunDetail>(`/api/runs/${id}`),
  templates: () => req<Template[]>("/api/templates"),
};

export function openEventSocket(onEvent: (e: any) => void): WebSocket {
  const ws = new WebSocket(`${WS_BASE}/ws/events`);
  ws.onmessage = (m) => {
    try {
      onEvent(JSON.parse(m.data));
    } catch {
      /* ignore */
    }
  };
  return ws;
}
