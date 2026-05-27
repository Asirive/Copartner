import { useState, useCallback } from "react";
import { AnimatePresence, motion } from "framer-motion";
import AmbientBar from "./components/AmbientBar";
import Dashboard from "./components/Dashboard";
import { useCopartnerWebSocket } from "./hooks/useWebSocket";
import { setDashboardMode, setBarMode } from "./windowCommands";
import "./App.css";

export default function App() {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isAmbientOn, setIsAmbientOn] = useState(false);

  const {
    connState,
    aiState,
    statusText,
    errorCount,
    messages,
    budget,
    suggestions,
    ambientStatus,
    sendQuery,
    sendWs,
    clearMessages,
    dismissSuggestion,
  } = useCopartnerWebSocket();

  const handleExpand = useCallback(async () => {
    setIsExpanded(true);
    await setDashboardMode();
  }, []);

  const handleMinimize = useCallback(async () => {
    setIsExpanded(false);
    await setBarMode();
  }, []);

  const handleToggleAmbient = useCallback(() => {
    const next = !isAmbientOn;
    setIsAmbientOn(next);
    sendWs("ambient_toggle", { active: next });
  }, [isAmbientOn, sendWs]);

  return (
    <div style={{ width: "100vw", height: "100vh", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {/* Always-visible Ambient Bar */}
      <AmbientBar
        connState={connState}
        aiState={aiState}
        statusText={statusText}
        errorCount={errorCount}
        isAmbientOn={isAmbientOn}
        onToggleAmbient={handleToggleAmbient}
        onExpand={handleExpand}
      />

      {/* Expandable Dashboard */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            key="dashboard"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }}
            style={{ overflow: "hidden", flex: 1 }}
          >
            <Dashboard
              messages={messages}
              budget={budget}
              ambientStatus={ambientStatus}
              connState={connState}
              onSendMessage={sendQuery}
              onClearMessages={clearMessages}
              onMinimize={handleMinimize}
              sendWs={sendWs}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Suggestion Toasts */}
      <AnimatePresence>
        {suggestions.map(sug => (
          <motion.div
            key={sug.id}
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.95 }}
            transition={{ duration: 0.2 }}
            style={{
              position: "fixed",
              bottom: 20,
              right: 20,
              maxWidth: 360,
              background: "rgba(14,14,14,0.95)",
              backdropFilter: "blur(12px)",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: 10,
              padding: "14px 16px",
              boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
              zIndex: 10000,
              display: "flex",
              flexDirection: "column",
              gap: 10,
            }}
          >
            <div style={{ fontSize: 12, color: "#ccc", lineHeight: 1.5 }}>{sug.text}</div>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button
                onClick={() => dismissSuggestion(sug.id)}
                style={{ background: "transparent", border: "none", color: "#666", fontSize: 11, cursor: "pointer", padding: "4px 8px" }}
              >
                Dismiss
              </button>
              <button
                onClick={() => { sendQuery(`Execute: ${sug.action}`); dismissSuggestion(sug.id); }}
                style={{ background: "#eaff00", color: "#000", border: "none", borderRadius: 5, fontSize: 11, fontWeight: 600, cursor: "pointer", padding: "5px 12px" }}
              >
                Accept
              </button>
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
