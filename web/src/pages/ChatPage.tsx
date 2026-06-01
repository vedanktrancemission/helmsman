import { useEffect, useRef, useState } from "react";
import { api, Agent } from "../lib/api";

interface Message {
  role: "user" | "agent";
  content: string;
}

interface ConversationMeta {
  thread_id: string;
  label: string;
  created_at: string;
}

const THREAD_KEY = (agentId: string) => `helmsman_thread_${agentId}`;
const THREADS_KEY = (agentId: string) => `helmsman_threads_${agentId}`;

function getThreads(agentId: string): ConversationMeta[] {
  try { return JSON.parse(localStorage.getItem(THREADS_KEY(agentId)) || "[]"); }
  catch { return []; }
}

function saveThread(agentId: string, thread: ConversationMeta) {
  const threads = getThreads(agentId).filter((t) => t.thread_id !== thread.thread_id);
  localStorage.setItem(THREADS_KEY(agentId), JSON.stringify([thread, ...threads]));
}

function deleteThread(agentId: string, threadId: string) {
  const threads = getThreads(agentId).filter((t) => t.thread_id !== threadId);
  localStorage.setItem(THREADS_KEY(agentId), JSON.stringify(threads));
  if (localStorage.getItem(THREAD_KEY(agentId)) === threadId)
    localStorage.removeItem(THREAD_KEY(agentId));
}

export default function ChatPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [threads, setThreads] = useState<ConversationMeta[]>([]);
  const [input, setInput] = useState("");
  const [threadId, setThreadId] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.listAgents().then((a) => {
      setAgents(a);
      if (a.length > 0) selectAgent(a[0]);
    });
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  const loadHistory = async (thread: string) => {
    if (!thread) return;
    setLoadingHistory(true);
    try {
      const history = await api.getChatHistory(thread);
      setMessages(history.map((m) => ({ role: m.role === "user" ? "user" : "agent", content: m.content })));
    } catch {
      setMessages([]);
    } finally {
      setLoadingHistory(false);
    }
  };

  const selectAgent = (agent: Agent) => {
    setSelectedAgent(agent);
    const savedThread = localStorage.getItem(THREAD_KEY(agent.id)) || "";
    setThreadId(savedThread);
    setMessages([]);
    setThreads(getThreads(agent.id));
    if (savedThread) loadHistory(savedThread);
  };

  const switchThread = async (meta: ConversationMeta) => {
    if (!selectedAgent) return;
    setThreadId(meta.thread_id);
    localStorage.setItem(THREAD_KEY(selectedAgent.id), meta.thread_id);
    setMessages([]);
    await loadHistory(meta.thread_id);
  };

  const startNewConversation = () => {
    if (!selectedAgent) return;
    localStorage.removeItem(THREAD_KEY(selectedAgent.id));
    setMessages([]);
    setThreadId("");
  };

  const removeThread = (e: React.MouseEvent, tid: string) => {
    e.stopPropagation();
    if (!selectedAgent) return;
    deleteThread(selectedAgent.id, tid);
    setThreads(getThreads(selectedAgent.id));
    if (threadId === tid) startNewConversation();
  };

  const send = async () => {
    if (!selectedAgent || !input.trim() || busy) return;
    const userMsg = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setBusy(true);
    try {
      const res = await api.chat(selectedAgent.id, userMsg, threadId);
      const newThread = res.thread_id;
      setThreadId(newThread);
      localStorage.setItem(THREAD_KEY(selectedAgent.id), newThread);

      // Save to thread list if this is the first message (new thread)
      const existing = getThreads(selectedAgent.id).find((t) => t.thread_id === newThread);
      if (!existing) {
        const meta: ConversationMeta = {
          thread_id: newThread,
          label: userMsg.slice(0, 60),
          created_at: new Date().toISOString(),
        };
        saveThread(selectedAgent.id, meta);
        setThreads(getThreads(selectedAgent.id));
      }

      setMessages((prev) => [...prev, { role: "agent", content: res.reply }]);
    } catch (err: any) {
      setMessages((prev) => [...prev, { role: "agent", content: `Error: ${err.message}` }]);
    } finally {
      setBusy(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  };

  return (
    <div style={{ display: "flex", height: "calc(100vh - 56px)" }}>

      {/* Sidebar — past conversations */}
      <div style={{ width: 220, borderRight: "1px solid var(--border)", display: "flex", flexDirection: "column", background: "var(--panel)", flexShrink: 0 }}>
        <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span className="label" style={{ margin: 0 }}>Conversations</span>
          <button onClick={startNewConversation} style={{ fontSize: 11, padding: "2px 8px" }}>+ New</button>
        </div>
        <div style={{ flex: 1, overflowY: "auto" }}>
          {threads.length === 0 && (
            <div className="muted" style={{ padding: "12px", fontSize: 12 }}>No past conversations</div>
          )}
          {threads.map((t) => (
            <div
              key={t.thread_id}
              onClick={() => switchThread(t)}
              style={{
                padding: "10px 12px",
                cursor: "pointer",
                borderBottom: "1px solid var(--border)",
                background: threadId === t.thread_id ? "var(--panel-2)" : "transparent",
                borderLeft: threadId === t.thread_id ? "3px solid var(--accent)" : "3px solid transparent",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
                gap: 4,
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {t.label || "Conversation"}
                </div>
                <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 2 }}>
                  {new Date(t.created_at).toLocaleDateString()}
                </div>
              </div>
              <span
                onClick={(e) => removeThread(e, t.thread_id)}
                style={{ fontSize: 14, color: "var(--muted)", cursor: "pointer", flexShrink: 0, lineHeight: 1 }}
                title="Delete"
              >×</span>
            </div>
          ))}
        </div>
      </div>

      {/* Main chat area */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {/* Header */}
        <div className="card" style={{ marginBottom: 0, borderRadius: 0, borderLeft: "none", borderRight: "none", borderTop: "none", display: "flex", gap: 12, alignItems: "center" }}>
          <span className="label" style={{ margin: 0, whiteSpace: "nowrap" }}>Agent:</span>
          <select
            value={selectedAgent?.id || ""}
            style={{ width: 200 }}
            onChange={(e) => {
              const agent = agents.find((a) => a.id === e.target.value) || null;
              if (agent) selectAgent(agent);
            }}
          >
            {agents.length === 0 && <option value="">No agents — create one first</option>}
            {agents.map((a) => (
              <option key={a.id} value={a.id}>{a.name} {a.role ? `(${a.role})` : ""}</option>
            ))}
          </select>
          {selectedAgent && (
            <span className="muted" style={{ fontSize: 12 }}>
              model: {selectedAgent.model}
              {selectedAgent.tools.length > 0 && ` · tools: ${selectedAgent.tools.join(", ")}`}
            </span>
          )}
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: "auto", padding: "16px 24px", display: "flex", flexDirection: "column", gap: 12 }}>
          {loadingHistory && (
            <div style={{ margin: "auto", color: "var(--muted)", fontSize: 13 }}>Loading conversation…</div>
          )}
          {!loadingHistory && messages.length === 0 && (
            <div style={{ margin: "auto", textAlign: "center" }}>
              <div className="muted" style={{ fontSize: 14 }}>
                {selectedAgent ? `Start a conversation with ${selectedAgent.name}` : "Select an agent above"}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} style={{ display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start" }}>
              <div style={{
                maxWidth: "70%", padding: "10px 14px", borderRadius: 12,
                background: m.role === "user" ? "var(--accent)" : "var(--panel-2)",
                color: m.role === "user" ? "#1a212b" : "var(--text)",
                border: m.role === "agent" ? "1px solid var(--border)" : "none",
                whiteSpace: "pre-wrap", lineHeight: 1.5, fontSize: 14,
              }}>
                {m.role === "agent" && (
                  <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 4 }}>{selectedAgent?.name}</div>
                )}
                {m.content}
              </div>
            </div>
          ))}
          {busy && (
            <div style={{ display: "flex", justifyContent: "flex-start" }}>
              <div style={{ padding: "10px 14px", borderRadius: 12, background: "var(--panel-2)", border: "1px solid var(--border)", color: "var(--muted)", fontSize: 14 }}>
                <span>{selectedAgent?.name} is thinking</span>
                <span className="typing-dots" />
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input bar */}
        <div className="card" style={{ borderRadius: 0, borderLeft: "none", borderRight: "none", borderBottom: "none", display: "flex", gap: 10, alignItems: "flex-end", padding: "12px 16px" }}>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={selectedAgent ? `Message ${selectedAgent.name}… (Enter to send, Shift+Enter for newline)` : "Select an agent first"}
            disabled={!selectedAgent || busy || loadingHistory}
            rows={1}
            style={{
              flex: 1, resize: "none", padding: "8px 12px", fontSize: 14,
              lineHeight: 1.5, minHeight: 38, maxHeight: 120,
              background: "var(--bg)", color: "var(--text)",
              border: "1px solid var(--border)", borderRadius: 8,
              outline: "none", fontFamily: "inherit",
            }}
            onInput={(e) => {
              const el = e.currentTarget;
              el.style.height = "auto";
              el.style.height = Math.min(el.scrollHeight, 120) + "px";
            }}
          />
          <button className="primary" onClick={send} disabled={!selectedAgent || !input.trim() || busy || loadingHistory} style={{ height: 38, padding: "0 20px" }}>
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
