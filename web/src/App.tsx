import { useState } from "react";
import AgentsPage from "./pages/AgentsPage";
import BuilderPage from "./pages/BuilderPage";
import ChatPage from "./pages/ChatPage";
import MonitorPage from "./pages/MonitorPage";

type Tab = "agents" | "builder" | "chat" | "monitor";

export default function App() {
  const [tab, setTab] = useState<Tab>("builder");
  return (
    <div className="app">
      <div className="topbar">
        <span className="brand">⎈ HELMSMAN</span>
        <div className="tabs">
          {(["agents", "builder", "chat", "monitor"] as Tab[]).map((t) => (
            <div
              key={t}
              className={`tab ${tab === t ? "active" : ""}`}
              onClick={() => setTab(t)}
            >
              {t[0].toUpperCase() + t.slice(1)}
            </div>
          ))}
        </div>
        <span className="muted" style={{ marginLeft: "auto" }}>
          AI Agent Orchestration Platform
        </span>
      </div>
      <div className="content" style={tab === "chat" ? { padding: 0 } : undefined}>
        {tab === "agents" && <AgentsPage />}
        {tab === "builder" && <BuilderPage />}
        {tab === "chat" && <ChatPage />}
        {tab === "monitor" && <MonitorPage />}
      </div>
    </div>
  );
}
