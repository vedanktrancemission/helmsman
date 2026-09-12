import { useState } from "react";
import { LayoutGroup, MotionConfig, motion } from "framer-motion";
import { Activity, Bot, MessagesSquare, Workflow } from "lucide-react";
import AgentsPage from "./pages/AgentsPage";
import BuilderPage from "./pages/BuilderPage";
import ChatPage from "./pages/ChatPage";
import MonitorPage from "./pages/MonitorPage";

const TABS = [
  { id: "agents", label: "Agents", Icon: Bot },
  { id: "builder", label: "Builder", Icon: Workflow },
  { id: "chat", label: "Chat", Icon: MessagesSquare },
  { id: "monitor", label: "Monitor", Icon: Activity },
] as const;

type Tab = (typeof TABS)[number]["id"];

/** Pages that lay themselves out edge to edge and manage their own scrolling. */
const FULL_BLEED: Tab[] = ["builder", "chat"];

export default function App() {
  const [tab, setTab] = useState<Tab>("builder");
  const fullBleed = FULL_BLEED.includes(tab);

  return (
    // reducedMotion="user" makes every spring below respect the OS setting.
    <MotionConfig reducedMotion="user">
      <div className="app">
        <nav className="rail">
          <div className="rail-brand" title="Helmsman">⎈</div>
          <LayoutGroup>
            <div className="rail-nav">
              {TABS.map(({ id, label, Icon }) => (
                <button
                  key={id}
                  className={`rail-item ${tab === id ? "active" : ""}`}
                  onClick={() => setTab(id)}
                  aria-current={tab === id}
                >
                  {tab === id && (
                    <motion.span
                      layoutId="rail-pill"
                      className="rail-pill"
                      transition={{ type: "spring", stiffness: 480, damping: 38 }}
                    />
                  )}
                  <span className="rail-item-content">
                    <Icon size={19} strokeWidth={1.9} />
                    <span className="rail-label">{label}</span>
                  </span>
                </button>
              ))}
            </div>
          </LayoutGroup>
          <div className="rail-foot" title="AI Agent Orchestration Platform">
            <span className="rail-dot" />
          </div>
        </nav>

        <main className="main">
          <div className={`content ${fullBleed ? "bleed" : ""}`}>
            {/* Keyed remount gives each tab a short rise-in on switch. */}
            <motion.div
              key={tab}
              className="page"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            >
              {tab === "agents" && <AgentsPage />}
              {tab === "builder" && <BuilderPage />}
              {tab === "chat" && <ChatPage />}
              {tab === "monitor" && <MonitorPage />}
            </motion.div>
          </div>
        </main>
      </div>
    </MotionConfig>
  );
}
