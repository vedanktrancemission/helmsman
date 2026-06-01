import { useEffect, useRef, useState } from "react";
import { api, Agent } from "../lib/api";

interface Message {
  role: "user" | "agent";
  content: string;
}

export default function ChatPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [threadId, setThreadId] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.listAgents().then((a) => {
      setAgents(a);
      if (a.length > 0) setSelectedAgent(a[0]);
    });
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  const startNewConversation = () => {
    setMessages([]);
    setThreadId("");
  };

  const send = async () => {
    if (!selectedAgent || !input.trim() || busy) return;
    const userMsg = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setBusy(true);
    try {
      const res = await api.chat(selectedAgent.id, userMsg, threadId);
      setThreadId(res.thread_id);
      setMessages((prev) => [...prev, { role: "agent", content: res.reply }]);
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        { role: "agent", content: `Error: ${err.message}` },
      ]);
    } finally {
      setBusy(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 56px)" }}>
      {/* Header */}
      <div className="card" style={{ marginBottom: 0, borderRadius: 0, borderLeft: "none", borderRight: "none", borderTop: "none", display: "flex", gap: 12, alignItems: "center" }}>
        <span className="label" style={{ margin: 0, whiteSpace: "nowrap" }}>Agent:</span>
        <select
          value={selectedAgent?.id || ""}
          style={{ width: 220 }}
          onChange={(e) => {
            const agent = agents.find((a) => a.id === e.target.value) || null;
            setSelectedAgent(agent);
            startNewConversation();
          }}
        >
          {agents.length === 0 && <option value="">No agents — create one first</option>}
          {agents.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name} {a.role ? `(${a.role})` : ""}
            </option>
          ))}
        </select>
        {selectedAgent && (
          <span className="muted" style={{ fontSize: 12 }}>
            model: {selectedAgent.model}
            {selectedAgent.tools.length > 0 && ` · tools: ${selectedAgent.tools.join(", ")}`}
          </span>
        )}
        <div style={{ marginLeft: "auto" }}>
          <button onClick={startNewConversation} disabled={messages.length === 0}>
            New conversation
          </button>
        </div>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", padding: "16px 24px", display: "flex", flexDirection: "column", gap: 12 }}>
        {messages.length === 0 && (
          <div style={{ margin: "auto", textAlign: "center" }}>
            <div className="muted" style={{ fontSize: 14 }}>
              {selectedAgent
                ? `Start a conversation with ${selectedAgent.name}`
                : "Select an agent above to start chatting"}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              justifyContent: m.role === "user" ? "flex-end" : "flex-start",
            }}
          >
            <div
              style={{
                maxWidth: "70%",
                padding: "10px 14px",
                borderRadius: 12,
                background: m.role === "user" ? "var(--accent)" : "var(--panel-2)",
                color: m.role === "user" ? "#1a212b" : "var(--text)",
                border: m.role === "agent" ? "1px solid var(--border)" : "none",
                whiteSpace: "pre-wrap",
                lineHeight: 1.5,
                fontSize: 14,
              }}
            >
              {m.role === "agent" && (
                <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 4 }}>
                  {selectedAgent?.name}
                </div>
              )}
              {m.content}
            </div>
          </div>
        ))}

        {busy && (
          <div style={{ display: "flex", justifyContent: "flex-start" }}>
            <div
              style={{
                padding: "10px 14px",
                borderRadius: 12,
                background: "var(--panel-2)",
                border: "1px solid var(--border)",
                color: "var(--muted)",
                fontSize: 14,
              }}
            >
              <span>{selectedAgent?.name} is thinking</span>
              <span className="typing-dots" />
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div
        className="card"
        style={{
          borderRadius: 0,
          borderLeft: "none",
          borderRight: "none",
          borderBottom: "none",
          display: "flex",
          gap: 10,
          alignItems: "flex-end",
          padding: "12px 16px",
        }}
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={selectedAgent ? `Message ${selectedAgent.name}… (Enter to send, Shift+Enter for newline)` : "Select an agent first"}
          disabled={!selectedAgent || busy}
          rows={1}
          style={{
            flex: 1,
            resize: "none",
            padding: "8px 12px",
            fontSize: 14,
            lineHeight: 1.5,
            minHeight: 38,
            maxHeight: 120,
            background: "var(--bg)",
            color: "var(--text)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            outline: "none",
            fontFamily: "inherit",
          }}
          onInput={(e) => {
            const el = e.currentTarget;
            el.style.height = "auto";
            el.style.height = Math.min(el.scrollHeight, 120) + "px";
          }}
        />
        <button
          className="primary"
          onClick={send}
          disabled={!selectedAgent || !input.trim() || busy}
          style={{ height: 38, padding: "0 20px" }}
        >
          Send
        </button>
      </div>
    </div>
  );
}
