import { motion } from "framer-motion";
import { Play, Pause, Expand, Wifi, WifiOff, Loader2, AlertCircle } from "lucide-react";
import type { ConnState, AIState } from "../hooks/useWebSocket";

interface AmbientBarProps {
  connState: ConnState;
  aiState: AIState;
  statusText: string;
  errorCount: number;
  isAmbientOn: boolean;
  isCollapsed: boolean;
  onToggleAmbient: () => void;
  onExpand: () => void;
}

function GlowIndicator({ state }: { state: AIState }) {
  const colors = {
    idle: "#333",
    watching: "#10B981",
    thinking: "#F59E0B",
    urgent: "#EF4444",
  };

  const animate = state === "thinking" || state === "urgent";

  return (
    <div style={{ position: "relative", width: 10, height: 10 }}>
      <motion.div
        animate={animate ? { scale: [1, 1.6, 1], opacity: [0.6, 1, 0.6] } : {}}
        transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
        style={{
          width: 10,
          height: 10,
          borderRadius: "50%",
          background: colors[state],
          boxShadow: `0 0 ${state === "urgent" ? 12 : 6}px ${colors[state]}`,
        }}
      />
    </div>
  );
}

function ConnDot({ state }: { state: ConnState }) {
  const color = state === "open" ? "#10B981" : state === "connecting" ? "#F59E0B" : "#EF4444";
  const Icon = state === "open" ? Wifi : state === "connecting" ? Loader2 : WifiOff;
  return (
    <div style={{ display: "flex", alignItems: "center" }} title={`Brain: ${state}`}>
      <Icon size={12} color={color} style={state === "connecting" ? { animation: "spin 1.5s linear infinite" } : {}} />
    </div>
  );
}

// Collapsed: just a 4px colored line
function CollapsedBar({ aiState, errorCount }: { aiState: AIState; errorCount: number }) {
  const colors = {
    idle: "rgba(50,50,50,0.6)",
    watching: "rgba(16,185,129,0.6)",
    thinking: "rgba(245,158,11,0.6)",
    urgent: "rgba(239,68,68,0.8)",
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      style={{
        width: "100%",
        height: 4,
        background: colors[aiState],
        boxShadow: aiState === "urgent" ? "0 0 8px rgba(239,68,68,0.5)" : "none",
        cursor: "default",
        position: "relative",
      }}
    >
      {errorCount > 0 && (
        <div
          style={{
            position: "absolute",
            right: 20,
            top: -5,
            width: 10,
            height: 10,
            borderRadius: "50%",
            background: "#EF4444",
            boxShadow: "0 0 4px rgba(239,68,68,0.6)",
          }}
        />
      )}
    </motion.div>
  );
}

export default function AmbientBar({
  connState,
  aiState,
  statusText,
  errorCount,
  isAmbientOn,
  isCollapsed,
  onToggleAmbient,
  onExpand,
}: AmbientBarProps) {
  if (isCollapsed) {
    return <CollapsedBar aiState={aiState} errorCount={errorCount} />;
  }

  return (
    <motion.div
      data-tauri-drag-region
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 40 }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.2 }}
      style={{
        width: "100%",
        height: 40,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 16px",
        background: "rgba(6,6,6,0.92)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        borderBottom: aiState === "urgent" ? "2px solid #EF4444" : "1px solid rgba(255,255,255,0.06)",
        boxShadow: aiState === "urgent"
          ? "0 4px 24px rgba(239,68,68,0.3)"
          : "0 2px 12px rgba(0,0,0,0.4)",
        cursor: "default",
        userSelect: "none",
        position: "relative",
        zIndex: 9999,
        flexShrink: 0,
      }}
    >
      {/* Left: Play/Stop + Brand */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
        <button
          onClick={(e) => { e.stopPropagation(); onToggleAmbient(); }}
          style={{
            background: isAmbientOn ? "rgba(16,185,129,0.15)" : "rgba(239,68,68,0.15)",
            border: "none",
            borderRadius: 6,
            width: 26,
            height: 26,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            cursor: "pointer",
            flexShrink: 0,
            transition: "background 0.15s",
          }}
          title={isAmbientOn ? "Pause ambient monitoring" : "Start ambient monitoring"}
        >
          {isAmbientOn ? (
            <Pause size={12} color="#10B981" />
          ) : (
            <Play size={12} color="#EF4444" />
          )}
        </button>

        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div
            style={{
              width: 16,
              height: 16,
              borderRadius: 4,
              background: "#eaff00",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 8,
              fontWeight: 800,
              color: "#000",
              flexShrink: 0,
            }}
          >
            A
          </div>
          <span style={{ fontSize: 12, fontWeight: 600, color: "#888", whiteSpace: "nowrap" }}>
            Copartner
          </span>
        </div>
      </div>

      {/* Center: Status Text */}
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 8,
          minWidth: 0,
          margin: "0 16px",
        }}
      >
        <GlowIndicator state={aiState} />
        <span
          style={{
            fontSize: 12,
            color: aiState === "urgent" ? "#EF4444" : "#aaa",
            fontWeight: aiState === "urgent" ? 600 : 400,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            maxWidth: "60vw",
          }}
        >
          {statusText}
        </span>
        {errorCount > 0 && (
          <span
            style={{
              display: "flex",
              alignItems: "center",
              gap: 3,
              background: "rgba(239,68,68,0.15)",
              color: "#EF4444",
              fontSize: 10,
              fontWeight: 600,
              padding: "1px 6px",
              borderRadius: 8,
              flexShrink: 0,
            }}
          >
            <AlertCircle size={10} />
            {errorCount}
          </span>
        )}
      </div>

      {/* Right: Connection + Expand */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
        <ConnDot state={connState} />
        <button
          onClick={(e) => { e.stopPropagation(); onExpand(); }}
          style={{
            background: "transparent",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: 5,
            width: 24,
            height: 24,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            cursor: "pointer",
            transition: "all 0.15s",
          }}
          onMouseEnter={e => {
            e.currentTarget.style.background = "rgba(255,255,255,0.08)";
            e.currentTarget.style.borderColor = "rgba(255,255,255,0.2)";
          }}
          onMouseLeave={e => {
            e.currentTarget.style.background = "transparent";
            e.currentTarget.style.borderColor = "rgba(255,255,255,0.1)";
          }}
          title="Expand dashboard"
        >
          <Expand size={12} color="#666" />
        </button>
      </div>
    </motion.div>
  );
}
