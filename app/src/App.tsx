import { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search, Terminal, Database, Settings, ArrowUp,
  Minus, Paperclip, Loader2, CheckCircle2, Clock,
  Trash2, ChevronDown, Wifi, WifiOff, Copy, Check,
  Sparkles, BrainCircuit, Zap
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./App.css";
import { getCurrentWindow, LogicalSize } from "@tauri-apps/api/window";

type ViewMode = "MINIMIZED" | "EXPANDED";
type SidebarTab = "stream" | "memory" | "prefs";
type ConnState = "connecting" | "open" | "closed" | "error";
type MsgStatus = "streaming" | "complete" | "error";

interface Message {
  id: string;
  role: "user" | "agent";
  text: string;
  timestamp: Date;
  toolBlocks?: ToolBlock[];
  status?: MsgStatus;
}

interface ToolBlock {
  name: string;
  status: "running" | "success" | "error";
  log: string;
}

interface MemoryEntry {
  id: string;
  label: string;
  category: string;
  timestamp: string;
}

interface Suggestion {
  id: string;
  text: string;
  action: string;
  confidence: number;
}

// ─── Window Management ───────────────────────────────────────────────────────
async function resizeAndShow(mode: ViewMode) {
  try {
    const win = getCurrentWindow();
    if (mode === "MINIMIZED") {
      await win.setSize(new LogicalSize(640, 56));
    } else {
      await win.setSize(new LogicalSize(1060, 740));
    }
    await win.center();
    await win.show();
    await win.setFocus();
  } catch (_) {}
}

let msgId = 0;

// ─── Root ────────────────────────────────────────────────────────────────────
export default function App() {
  const [viewMode, setViewMode] = useState<ViewMode>("MINIMIZED");
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [connState, setConnState] = useState<ConnState>("connecting");
  const [ambientStatus, setAmbientStatus] = useState<Record<string, string>>({});
  const wsRef = useRef<WebSocket | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const dashInputRef = useRef<HTMLInputElement>(null);
  const pendingIdRef = useRef<string | null>(null);

  // ─── WebSocket Lifecycle ───────────────────────────────────────────────────
  useEffect(() => {
    const connect = () => {
      setConnState("connecting");
      const ws = new WebSocket("ws://127.0.0.1:8765");
      wsRef.current = ws;

      ws.onopen = () => {
        setConnState("open");
        console.log("[Copartner] WebSocket connected");
      };

      ws.onclose = () => {
        setConnState("closed");
        console.log("[Copartner] WebSocket closed — reconnecting in 3s");
        setTimeout(connect, 3000);
      };

      ws.onerror = () => {
        setConnState("error");
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          handleServerMessage(data);
        } catch (e) {
          console.error("[Copartner] Bad WS message:", event.data);
        }
      };
    };

    connect();
    return () => {
      wsRef.current?.close();
    };
  }, []);

  // ─── Message Handlers ──────────────────────────────────────────────────────
  const handleServerMessage = useCallback((data: any) => {
    const type = data.type;
    const payload = data.payload || {};

    if (type === "stream_chunk") {
      const pid = pendingIdRef.current;
      if (!pid) return;
      setMessages(prev =>
        prev.map(m =>
          m.id === pid
            ? { ...m, text: m.text + payload.text, status: "streaming" as MsgStatus }
            : m
        )
      );
    } else if (type === "final_answer") {
      const pid = pendingIdRef.current;
      if (!pid) return;
      // Strip <final_answer> tags for display
      let cleanText = payload.text || "";
      cleanText = cleanText.replace(/<final_answer>/g, "").replace(/<\/final_answer>/g, "").trim();
      setMessages(prev =>
        prev.map(m =>
          m.id === pid
            ? { ...m, text: cleanText, status: "complete" as MsgStatus }
            : m
        )
      );
      pendingIdRef.current = null;
    } else if (type === "error") {
      const pid = pendingIdRef.current;
      if (pid) {
        setMessages(prev =>
          prev.map(m =>
            m.id === pid
              ? { ...m, text: "**Error:** " + payload.message, status: "error" as MsgStatus }
              : m
          )
        );
        pendingIdRef.current = null;
      }
    } else if (type === "state_update") {
      if (payload.ambient) {
        setAmbientStatus(payload.ambient);
      }
    } else if (type === "proactive_suggestion") {
      const sug: Suggestion = {
        id: payload.id,
        text: payload.text,
        action: payload.action,
        confidence: payload.confidence,
      };
      setSuggestions(prev => [...prev, sug]);
    }
  }, []);

  // ─── UI Effects ────────────────────────────────────────────────────────────
  useEffect(() => {
    resizeAndShow(viewMode);
    if (viewMode === "MINIMIZED") setTimeout(() => inputRef.current?.focus(), 200);
    else setTimeout(() => dashInputRef.current?.focus(), 200);
  }, [viewMode]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && viewMode === "EXPANDED") setViewMode("MINIMIZED");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [viewMode]);

  // ─── Sending ─────────────────────────────────────────────────────────────────
  const submitMessage = useCallback((text: string) => {
    if (!text.trim()) return;
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      alert("Copartner brain is not connected. Start: python core/copartner_server.py");
      return;
    }

    const userMsg: Message = {
      id: String(++msgId),
      role: "user",
      text: text.trim(),
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, userMsg]);

    // Create pending agent message
    const pendingId = String(++msgId);
    pendingIdRef.current = pendingId;
    const pendingMsg: Message = {
      id: pendingId,
      role: "agent",
      text: "",
      timestamp: new Date(),
      status: "streaming",
    };
    setMessages(prev => [...prev, pendingMsg]);

    ws.send(JSON.stringify({
      type: "query",
      payload: { text: text.trim() }
    }));
  }, []);

  const submitSpotlight = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    submitMessage(query);
    setQuery("");
    setViewMode("EXPANDED");
  };

  const submitDash = (e: React.FormEvent) => {
    e.preventDefault();
    const el = dashInputRef.current;
    if (!el || !el.value.trim()) return;
    submitMessage(el.value);
    el.value = "";
  };

  const clearMessages = () => setMessages([]);

  const acceptSuggestion = (sug: Suggestion) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "suggestion_action", payload: { id: sug.id, action: sug.action } }));
      submitMessage(`Execute suggestion: ${sug.text}`);
    }
    setSuggestions(prev => prev.filter(s => s.id !== sug.id));
  };

  const dismissSuggestion = (sug: Suggestion, neverAgain: boolean = false) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      if (neverAgain) {
        ws.send(JSON.stringify({ type: "suggestion_block", payload: { action: sug.action } }));
      } else {
        ws.send(JSON.stringify({ type: "suggestion_dismiss", payload: { id: sug.id, never_again: false } }));
      }
    }
    setSuggestions(prev => prev.filter(s => s.id !== sug.id));
  };

  return (
    <div style={{ width: "100vw", height: "100vh", background: "transparent", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <AnimatePresence mode="wait">
        {viewMode === "MINIMIZED" ? (
          <Spotlight key="s" query={query} setQuery={setQuery} onSubmit={submitSpotlight} inputRef={inputRef} connState={connState} />
        ) : (
          <Dashboard
            key="d"
            messages={messages}
            onMinimize={() => setViewMode("MINIMIZED")}
            dashInputRef={dashInputRef}
            onSubmit={submitDash}
            onClear={clearMessages}
            connState={connState}
            ambientStatus={ambientStatus}
          />
        )}
      </AnimatePresence>
      <SuggestionsOverlay suggestions={suggestions} onAccept={acceptSuggestion} onDismiss={dismissSuggestion} />
    </div>
  );
}

// ─── Spotlight ────────────────────────────────────────────────────────────────
function Spotlight({ query, setQuery, onSubmit, inputRef, connState }: any) {
  return (
    <motion.div
      data-tauri-drag-region
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      transition={{ duration: 0.18, ease: [0.25, 0.1, 0.25, 1] }}
      style={{
        width: "100%", height: "100%",
        display: "flex", alignItems: "center", padding: "0 18px", gap: "12px",
        background: "rgba(6,6,6,0.94)",
        backdropFilter: "blur(24px)", WebkitBackdropFilter: "blur(24px)",
        borderRadius: "10px",
        border: "1px solid rgba(255,255,255,0.06)",
        boxShadow: "0 4px 24px rgba(0,0,0,0.5)",
      }}
    >
      <Search size={16} color="#666" style={{ flexShrink: 0 }} />
      <form onSubmit={onSubmit} style={{ flex: 1 }}>
        <input ref={inputRef} type="text" value={query} onChange={e => setQuery(e.target.value)}
          placeholder="What do you want to build?"
          style={{ width: "100%", background: "transparent", border: "none", outline: "none", color: "#ddd", fontSize: "15px", fontFamily: "var(--font-sans)" }}
        />
      </form>
      <ConnDot state={connState} />
      <kbd style={{ fontSize: "10px", color: "#555", background: "#181818", border: "1px solid #2a2a2a", borderRadius: "3px", padding: "2px 5px", fontFamily: "var(--font-sans)" }}>↵</kbd>
    </motion.div>
  );
}

// ─── Dashboard ───────────────────────────────────────────────────────────────
function Dashboard({ messages, onMinimize, dashInputRef, onSubmit, onClear, connState, ambientStatus }: any) {
  const [activeTab, setActiveTab] = useState<SidebarTab>("stream");
  const feedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight;
  }, [messages]);

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.99 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.99 }}
      transition={{ duration: 0.2, ease: [0.25, 0.1, 0.25, 1] }}
      style={{
        width: "100%", height: "100%",
        display: "flex", background: "#050505",
        borderRadius: "10px", border: "1px solid #1a1a1a",
        boxShadow: "0 24px 64px rgba(0,0,0,0.85)",
        overflow: "hidden",
      }}
    >
      {/* ─ Sidebar ─ */}
      <div style={{ width: "220px", flexShrink: 0, background: "#080808", borderRight: "1px solid #1a1a1a", display: "flex", flexDirection: "column" }}>
        
        {/* Brand */}
        <div data-tauri-drag-region style={{ height: "52px", display: "flex", alignItems: "center", padding: "0 16px", gap: "8px", cursor: "grab", borderBottom: "1px solid #141414" }}>
          <div style={{ width: "22px", height: "22px", borderRadius: "5px", background: "#eaff00", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <span style={{ fontSize: "11px", fontWeight: 800, color: "#000", letterSpacing: "-0.5px" }}>A</span>
          </div>
          <span style={{ fontSize: "13px", fontWeight: 600, color: "#ccc" }}>Copartner</span>
          <span style={{ fontSize: "10px", color: "#444", marginLeft: "auto" }}>v0.1</span>
        </div>

        {/* Nav */}
        <nav style={{ padding: "10px 8px", display: "flex", flexDirection: "column", gap: "1px" }}>
          <NavBtn icon={<Terminal size={15} />} label="Stream" active={activeTab === "stream"} onClick={() => setActiveTab("stream")} />
          <NavBtn icon={<Database size={15} />} label="Memory" active={activeTab === "memory"} onClick={() => setActiveTab("memory")} />
          <NavBtn icon={<Settings size={15} />} label="Preferences" active={activeTab === "prefs"} onClick={() => setActiveTab("prefs")} />
        </nav>

        <div style={{ padding: "12px 8px 4px 8px" }}>
          <div style={{ fontSize: "10px", fontWeight: 600, color: "#444", textTransform: "uppercase", letterSpacing: "0.06em", padding: "0 8px 6px" }}>Workspaces</div>
          <NavBtn icon={<Badge>S</Badge>} label="SNAP-C1" />
          <NavBtn icon={<Badge>T</Badge>} label="Tauri App" />
        </div>

        <div style={{ marginTop: "auto", padding: "8px", borderTop: "1px solid #141414" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", padding: "8px 10px", borderRadius: "5px", cursor: "pointer" }}>
            <div style={{ width: "24px", height: "24px", borderRadius: "50%", background: "#1a1a1a", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "10px", color: "#666", fontWeight: 600 }}>H</div>
            <div>
              <div style={{ fontSize: "12px", color: "#999" }}>Haziq</div>
              <div style={{ fontSize: "10px", color: "#444" }}>Local</div>
            </div>
          </div>
        </div>

        {/* Ambient Status */}
        {ambientStatus && Object.keys(ambientStatus).length > 0 && (
          <div style={{ padding: "8px", borderTop: "1px solid #141414" }}>
            <div style={{ fontSize: "10px", fontWeight: 600, color: "#444", textTransform: "uppercase", letterSpacing: "0.06em", padding: "0 8px 6px" }}>Ambient</div>
            {ambientStatus.screen_observer && (
              <div style={{ fontSize: "10px", color: "#555", padding: "2px 8px" }}>
                Screen: {ambientStatus.screen_observer}
              </div>
            )}
            {ambientStatus.ide_watcher && (
              <div style={{ fontSize: "10px", color: "#555", padding: "2px 8px" }}>
                IDE: {ambientStatus.ide_watcher}
              </div>
            )}
            {ambientStatus.proactive_mode && (
              <div style={{ fontSize: "10px", color: "#555", padding: "2px 8px" }}>
                Mode: {ambientStatus.proactive_mode}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ─ Main ─ */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>

        {/* Header */}
        <div data-tauri-drag-region style={{
          height: "52px", flexShrink: 0, borderBottom: "1px solid #1a1a1a",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "0 20px", cursor: "grab",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <div style={{ fontSize: "13px", fontWeight: 600, color: "#bbb" }}>
              {activeTab === "stream" && "Interaction Stream"}
              {activeTab === "memory" && "Memory Explorer"}
              {activeTab === "prefs" && "Preferences"}
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            {activeTab === "stream" && messages.length > 0 && (
              <button onClick={onClear} style={{ background: "transparent", border: "none", color: "#444", cursor: "pointer", padding: "4px", display: "flex" }}
                title="Clear conversation"
              >
                <Trash2 size={14} />
              </button>
            )}
            <ConnPill state={connState} />
            <button onClick={onMinimize} style={{ background: "transparent", border: "none", color: "#555", cursor: "pointer", padding: "4px", display: "flex", borderRadius: "3px" }}
              onMouseEnter={e => (e.currentTarget.style.background = "#1a1a1a")}
              onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
            >
              <Minus size={14} />
            </button>
          </div>
        </div>

        {/* ─ Content Area ─ */}
        {activeTab === "stream" && (
          <StreamView messages={messages} feedRef={feedRef} dashInputRef={dashInputRef} onSubmit={onSubmit} />
        )}
        {activeTab === "memory" && <MemoryView />}
        {activeTab === "prefs" && <PrefsView />}
      </div>
    </motion.div>
  );
}

// ─── Connection Indicators ───────────────────────────────────────────────────
function ConnDot({ state }: { state: ConnState }) {
  const color = state === "open" ? "#10B981" : state === "connecting" ? "#F59E0B" : "#EF4444";
  const Icon = state === "open" ? Wifi : state === "connecting" ? Loader2 : WifiOff;
  return (
    <div style={{ display: "flex", alignItems: "center" }} title={`Brain: ${state}`}>
      <Icon size={14} color={color} style={state === "connecting" ? { animation: "spin 1.5s linear infinite" } : {}} />
    </div>
  );
}

function ConnPill({ state }: { state: ConnState }) {
  const color = state === "open" ? "#10B981" : state === "connecting" ? "#F59E0B" : "#EF4444";
  const label = state === "open" ? "Connected" : state === "connecting" ? "Connecting" : "Offline";
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: "5px",
      padding: "3px 8px", background: "#111", border: "1px solid #1e1e1e",
      borderRadius: "12px", fontSize: "11px", color: "#666",
    }}>
      <span style={{ width: "5px", height: "5px", borderRadius: "50%", background: color, display: "inline-block" }} />
      {label}
    </div>
  );
}

// ─── Stream View ─────────────────────────────────────────────────────────────
function StreamView({ messages, feedRef, dashInputRef, onSubmit }: any) {
  return (
    <>
      <div ref={feedRef} style={{ flex: 1, overflowY: "auto", padding: "24px 28px", display: "flex", flexDirection: "column", gap: "24px" }}>
        {messages.length === 0 ? <EmptyStream /> : messages.map((m: Message) => <MsgRow key={m.id} msg={m} />)}
      </div>
      <div style={{ padding: "0 24px 20px", flexShrink: 0 }}>
        <form onSubmit={onSubmit}>
          <div style={{
            background: "#0e0e0e", border: "1px solid #1e1e1e", borderRadius: "8px",
            padding: "12px 14px", display: "flex", alignItems: "center", gap: "10px",
            transition: "border-color 0.15s",
          }}
            onFocus={e => (e.currentTarget.style.borderColor = "#333")}
            onBlur={e => (e.currentTarget.style.borderColor = "#1e1e1e")}
          >
            <Paperclip size={15} color="#444" style={{ cursor: "pointer", flexShrink: 0 }} />
            <input ref={dashInputRef} type="text" placeholder="Message Copartner…"
              style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: "#ccc", fontSize: "13px", fontFamily: "var(--font-sans)" }}
            />
            <button type="submit" style={{
              background: "#eee", color: "#000", border: "none", borderRadius: "5px",
              width: "28px", height: "28px", display: "flex", alignItems: "center", justifyContent: "center",
              cursor: "pointer", flexShrink: 0,
            }}>
              <ArrowUp size={14} />
            </button>
          </div>
        </form>
      </div>
    </>
  );
}

// ─── Memory View ─────────────────────────────────────────────────────────────
const MOCK_MEMORIES: MemoryEntry[] = [
  { id: "1", label: "SNAP-C1 uses MoLoRA architecture for parameter-efficient training", category: "Architecture", timestamp: "2h ago" },
  { id: "2", label: "Team Thinking adapter trained with v2 data (40 examples, 8 epochs)", category: "Training", timestamp: "5h ago" },
  { id: "3", label: "Tauri app uses frameless, transparent window with global shortcut", category: "Frontend", timestamp: "12m ago" },
  { id: "4", label: "Swiss Modernism design system selected for Copartner UI", category: "Design", timestamp: "30m ago" },
  { id: "5", label: "DPO training pipeline configured in training/auto_finetune.py", category: "Training", timestamp: "1d ago" },
];

function MemoryView() {
  const [filter, setFilter] = useState("all");
  const categories = ["all", ...Array.from(new Set(MOCK_MEMORIES.map(m => m.category)))];
  const filtered = filter === "all" ? MOCK_MEMORIES : MOCK_MEMORIES.filter(m => m.category === filter);

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px", display: "flex", flexDirection: "column", gap: "16px" }}>
      <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
        {categories.map(cat => (
          <button key={cat} onClick={() => setFilter(cat)} style={{
            padding: "4px 12px", borderRadius: "4px", fontSize: "11px", fontWeight: 500, border: "1px solid #1e1e1e",
            cursor: "pointer", fontFamily: "var(--font-sans)",
            background: filter === cat ? "#1e1e1e" : "transparent",
            color: filter === cat ? "#ccc" : "#555",
          }}>
            {cat === "all" ? "All" : cat}
          </button>
        ))}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
        {filtered.map(mem => (
          <div key={mem.id} style={{
            padding: "12px 14px", borderRadius: "6px", cursor: "pointer",
            display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "12px",
            transition: "background 0.1s",
          }}
            onMouseEnter={e => (e.currentTarget.style.background = "#111")}
            onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
          >
            <div>
              <div style={{ fontSize: "13px", color: "#bbb", lineHeight: 1.5 }}>{mem.label}</div>
              <div style={{ fontSize: "11px", color: "#444", marginTop: "4px" }}>{mem.category}</div>
            </div>
            <div style={{ fontSize: "11px", color: "#444", flexShrink: 0, marginTop: "2px" }}>{mem.timestamp}</div>
          </div>
        ))}
      </div>

      <div style={{ marginTop: "auto", padding: "16px 0 0", borderTop: "1px solid #141414", display: "flex", gap: "20px" }}>
        <Stat label="Stored" value={String(MOCK_MEMORIES.length)} />
        <Stat label="Categories" value={String(categories.length - 1)} />
        <Stat label="Last Updated" value="12m ago" />
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={{ fontSize: "16px", fontWeight: 600, color: "#bbb", fontVariantNumeric: "tabular-nums" }}>{value}</div>
      <div style={{ fontSize: "10px", color: "#444", marginTop: "2px" }}>{label}</div>
    </div>
  );
}

// ─── Preferences View ────────────────────────────────────────────────────────
function PrefsView() {
  const [theme, setTheme] = useState("dark");
  const [keybind] = useState("Ctrl+Space");
  const [alwaysOnTop, setAlwaysOnTop] = useState(true);

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
        <PrefSection title="Appearance">
          <PrefRow label="Theme" description="Controls the global color scheme">
            <select value={theme} onChange={e => setTheme(e.target.value)} style={{
              background: "#111", border: "1px solid #222", borderRadius: "4px", color: "#aaa",
              padding: "4px 8px", fontSize: "12px", fontFamily: "var(--font-sans)", outline: "none",
            }}>
              <option value="dark">Dark</option>
              <option value="light">Light (coming soon)</option>
            </select>
          </PrefRow>
        </PrefSection>

        <PrefSection title="Keybindings">
          <PrefRow label="Toggle Spotlight" description="Global shortcut to summon Copartner">
            <kbd style={{ fontSize: "11px", color: "#888", background: "#111", border: "1px solid #222", borderRadius: "3px", padding: "3px 8px", fontFamily: "var(--font-mono)" }}>
              {keybind}
            </kbd>
          </PrefRow>
        </PrefSection>

        <PrefSection title="Behavior">
          <PrefRow label="Always on top" description="Keep Copartner above other windows">
            <Toggle checked={alwaysOnTop} onChange={setAlwaysOnTop} />
          </PrefRow>
        </PrefSection>
      </div>
    </div>
  );
}

function PrefSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: "20px" }}>
      <div style={{ fontSize: "11px", fontWeight: 600, color: "#555", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "8px" }}>{title}</div>
      <div style={{ display: "flex", flexDirection: "column", gap: "1px", background: "#0e0e0e", borderRadius: "6px", border: "1px solid #1a1a1a", overflow: "hidden" }}>
        {children}
      </div>
    </div>
  );
}

function PrefRow({ label, description, children }: { label: string; description: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 14px", gap: "16px" }}>
      <div>
        <div style={{ fontSize: "13px", color: "#bbb" }}>{label}</div>
        <div style={{ fontSize: "11px", color: "#444", marginTop: "2px" }}>{description}</div>
      </div>
      {children}
    </div>
  );
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div onClick={() => onChange(!checked)} style={{
      width: "36px", height: "20px", borderRadius: "10px", cursor: "pointer",
      background: checked ? "#3B82F6" : "#222", transition: "background 0.2s",
      position: "relative", flexShrink: 0,
    }}>
      <div style={{
        width: "16px", height: "16px", borderRadius: "50%", background: "#fff",
        position: "absolute", top: "2px", transition: "left 0.2s",
        left: checked ? "18px" : "2px",
      }} />
    </div>
  );
}

// ─── Shared Components ───────────────────────────────────────────────────────
function EmptyStream() {
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "40px 0" }}>
      <div style={{ 
        width: "48px", height: "48px", borderRadius: "12px", 
        background: "#111", border: "1px solid #1a1a1a",
        display: "flex", alignItems: "center", justifyContent: "center",
        marginBottom: "16px"
      }}>
        <Sparkles size={20} color="#555" />
      </div>
      <div style={{ fontSize: "14px", fontWeight: 500, color: "#666", marginBottom: "4px" }}>No messages yet.</div>
      <div style={{ fontSize: "12px", color: "#444" }}>Type below to start building.</div>
    </div>
  );
}

function MsgRow({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  const isStreaming = msg.status === "streaming";
  const isComplete = msg.status === "complete";
  const isError = msg.status === "error";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: [0.25, 0.1, 0.25, 1] }}
      style={{ display: "flex", gap: "12px", alignItems: "flex-start" }}
    >
      {/* Avatar */}
      <div style={{
        width: "28px", height: "28px", borderRadius: "8px", flexShrink: 0,
        background: isUser ? "#1a1a1a" : "#eee",
        border: isUser ? "1px solid #2a2a2a" : "none",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: "11px", fontWeight: 600, color: isUser ? "#888" : "#000",
      }}>
        {isUser ? (
          <span>H</span>
        ) : (
          <BrainCircuit size={14} color="#000" />
        )}
      </div>

      {/* Content */}
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: "4px" }}>
        {/* Author + Status */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span style={{ fontSize: "12px", fontWeight: 600, color: isUser ? "#888" : "#ccc" }}>
            {isUser ? "You" : "Copartner"}
          </span>
          {isStreaming && (
            <span style={{ fontSize: "11px", color: "#3B82F6", display: "flex", alignItems: "center", gap: "4px" }}>
              <Zap size={10} style={{ animation: "pulse 1.5s ease-in-out infinite" }} />
              thinking...
            </span>
          )}
          {isComplete && (
            <span style={{ fontSize: "11px", color: "#10B981", display: "flex", alignItems: "center", gap: "4px" }}>
              <CheckCircle2 size={10} />
              done
            </span>
          )}
          {isError && (
            <span style={{ fontSize: "11px", color: "#EF4444", display: "flex", alignItems: "center", gap: "4px" }}>
              <Clock size={10} />
              error
            </span>
          )}
        </div>

        {/* Tool Blocks */}
        {msg.toolBlocks?.map((tool, i) => (
          <ToolBlockUI key={i} tool={tool} />
        ))}

        {/* Message Body */}
        <div style={{ 
          fontSize: "13.5px", 
          lineHeight: 1.6, 
          color: isUser ? "#ccc" : "#bbb",
          paddingTop: msg.toolBlocks ? "8px" : "2px"
        }}>
          {isUser ? (
            <span>{msg.text}</span>
          ) : isStreaming && !msg.text ? (
            <div style={{ display: "flex", alignItems: "center", gap: "8px", padding: "8px 0" }}>
              <Loader2 size={16} color="#3B82F6" style={{ animation: "spin 1.5s linear infinite" }} />
              <span style={{ fontSize: "13px", color: "#555" }}>Copartner is thinking...</span>
            </div>
          ) : (
            <MarkdownRenderer content={msg.text} />
          )}
          {isStreaming && msg.text && (
            <span style={{ 
              display: "inline-block", 
              width: "2px", 
              height: "16px", 
              background: "#3B82F6", 
              marginLeft: "3px", 
              verticalAlign: "middle",
              borderRadius: "1px",
              animation: "blink 1s step-end infinite" 
            }} />
          )}
        </div>
      </div>
    </motion.div>
  );
}

// ─── Markdown Renderer ─────────────────────────────────────────────────────
function MarkdownRenderer({ content }: { content: string }) {
  const [copied, setCopied] = useState(false);

  const copyCode = (code: string) => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ node, inline, className, children, ...props }: any) {
            const code = String(children).replace(/\n$/, "");
            if (inline) {
              return (
                <code className="inline-code" {...props}>
                  {children}
                </code>
              );
            }
            return (
              <div style={{ position: "relative", margin: "12px 0" }}>
                <div style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "8px 12px", background: "#0a0a0a", border: "1px solid #1a1a1a",
                  borderBottom: "none", borderRadius: "6px 6px 0 0",
                }}>
                  <span style={{ fontSize: "10px", color: "#555", fontFamily: "var(--font-mono)" }}>
                    {className?.replace("language-", "") || "code"}
                  </span>
                  <button
                    onClick={() => copyCode(code)}
                    style={{
                      background: "transparent", border: "none", color: "#555",
                      cursor: "pointer", padding: "2px", display: "flex",
                      borderRadius: "3px",
                    }}
                    title="Copy code"
                  >
                    {copied ? <Check size={12} color="#10B981" /> : <Copy size={12} />}
                  </button>
                </div>
                <pre style={{
                  margin: 0,
                  padding: "12px",
                  background: "#080808",
                  border: "1px solid #1a1a1a",
                  borderTop: "none",
                  borderRadius: "0 0 6px 6px",
                  overflow: "auto",
                  fontSize: "12px",
                  lineHeight: 1.6,
                }}>
                  <code {...props} style={{ fontFamily: "var(--font-mono)", color: "#a0a0a0" }}>
                    {children}
                  </code>
                </pre>
              </div>
            );
          },
          p({ children }: any) {
            return <p style={{ margin: "8px 0", lineHeight: 1.6 }}>{children}</p>;
          },
          ul({ children }: any) {
            return <ul style={{ margin: "8px 0", paddingLeft: "20px", color: "#bbb" }}>{children}</ul>;
          },
          ol({ children }: any) {
            return <ol style={{ margin: "8px 0", paddingLeft: "20px", color: "#bbb" }}>{children}</ol>;
          },
          li({ children }: any) {
            return <li style={{ margin: "4px 0", lineHeight: 1.6 }}>{children}</li>;
          },
          h1({ children }: any) {
            return <h1 style={{ fontSize: "18px", fontWeight: 700, color: "#eee", margin: "16px 0 8px", borderBottom: "1px solid #1a1a1a", paddingBottom: "8px" }}>{children}</h1>;
          },
          h2({ children }: any) {
            return <h2 style={{ fontSize: "16px", fontWeight: 600, color: "#ddd", margin: "14px 0 6px" }}>{children}</h2>;
          },
          h3({ children }: any) {
            return <h3 style={{ fontSize: "14px", fontWeight: 600, color: "#ccc", margin: "12px 0 6px" }}>{children}</h3>;
          },
          blockquote({ children }: any) {
            return (
              <blockquote style={{
                margin: "12px 0",
                padding: "8px 12px",
                borderLeft: "3px solid #3B82F6",
                background: "#0a0a0a",
                borderRadius: "0 6px 6px 0",
                color: "#999",
              }}>
                {children}
              </blockquote>
            );
          },
          a({ href, children }: any) {
            return <a href={href} target="_blank" rel="noopener noreferrer" style={{ color: "#3B82F6", textDecoration: "none" }}>{children}</a>;
          },
          strong({ children }: any) {
            return <strong style={{ color: "#eee", fontWeight: 600 }}>{children}</strong>;
          },
          hr() {
            return <hr style={{ border: "none", borderTop: "1px solid #1a1a1a", margin: "16px 0" }} />;
          },
          table({ children }: any) {
            return (
              <div style={{ overflow: "auto", margin: "12px 0" }}>
                <table style={{ borderCollapse: "collapse", fontSize: "12px", width: "100%" }}>
                  {children}
                </table>
              </div>
            );
          },
          thead({ children }: any) {
            return <thead style={{ background: "#0e0e0e" }}>{children}</thead>;
          },
          th({ children }: any) {
            return <th style={{ padding: "8px 12px", border: "1px solid #1a1a1a", textAlign: "left", fontWeight: 600, color: "#ccc", fontSize: "12px" }}>{children}</th>;
          },
          td({ children }: any) {
            return <td style={{ padding: "8px 12px", border: "1px solid #1a1a1a", color: "#aaa" }}>{children}</td>;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

// ─── Tool Block UI ───────────────────────────────────────────────────────────
function ToolBlockUI({ tool }: { tool: ToolBlock }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div style={{ marginBottom: "6px", border: "1px solid #1a1a1a", borderRadius: "6px", overflow: "hidden", background: "#0a0a0a" }}>
      <div onClick={() => setExpanded(!expanded)} style={{
        display: "flex", alignItems: "center", gap: "8px",
        padding: "8px 12px", cursor: "pointer", fontSize: "12px",
        fontFamily: "var(--font-mono)", color: "#888",
      }}>
        {tool.status === "running" ? (
          <Loader2 size={13} color="#3B82F6" style={{ animation: "spin 1.5s linear infinite" }} />
        ) : tool.status === "success" ? (
          <CheckCircle2 size={13} color="#10B981" />
        ) : (
          <Clock size={13} color="#EF4444" />
        )}
        <span style={{ flex: 1 }}>{tool.name}</span>
        <ChevronDown size={12} color="#444" style={{ transform: expanded ? "rotate(180deg)" : "rotate(0)", transition: "transform 0.15s" }} />
      </div>
      {expanded && tool.log && (
        <div style={{
          padding: "10px 12px", borderTop: "1px solid #141414",
          fontSize: "11px", fontFamily: "var(--font-mono)", color: "#555",
          lineHeight: 1.6, whiteSpace: "pre-wrap", background: "#050505",
        }}>
          {tool.log}
        </div>
      )}
    </div>
  );
}

function NavBtn({ icon, label, active, onClick }: any) {
  return (
    <div onClick={onClick} style={{
      display: "flex", alignItems: "center", gap: "8px",
      padding: "7px 10px", borderRadius: "5px", cursor: "pointer",
      fontSize: "12px", fontWeight: 500,
      color: active ? "#ccc" : "#666",
      background: active ? "#141414" : "transparent",
      transition: "all 0.1s",
    }}
      onMouseEnter={e => { if (!active) e.currentTarget.style.background = "#0f0f0f"; }}
      onMouseLeave={e => { if (!active) e.currentTarget.style.background = "transparent"; }}
    >
      {icon}
      {label}
    </div>
  );
}

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      width: "16px", height: "16px", borderRadius: "3px", background: "#111",
      border: "1px solid #222", display: "flex", alignItems: "center",
      justifyContent: "center", fontSize: "9px", fontWeight: 700, color: "#555",
    }}>
      {children}
    </div>
  );
}

// ─── Suggestions Overlay ─────────────────────────────────────────────────────
function SuggestionsOverlay({ suggestions, onAccept, onDismiss }: {
  suggestions: Suggestion[];
  onAccept: (s: Suggestion) => void;
  onDismiss: (s: Suggestion, neverAgain: boolean) => void;
}) {
  if (suggestions.length === 0) return null;

  return (
    <div style={{
      position: "fixed",
      bottom: "20px",
      right: "20px",
      display: "flex",
      flexDirection: "column",
      gap: "8px",
      zIndex: 9999,
      maxWidth: "360px",
    }}>
      <AnimatePresence>
        {suggestions.map(sug => (
          <motion.div
            key={sug.id}
            initial={{ opacity: 0, x: 20, scale: 0.95 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 20, scale: 0.95 }}
            transition={{ duration: 0.2 }}
            style={{
              background: "#111",
              border: "1px solid #222",
              borderRadius: "8px",
              padding: "12px 14px",
              boxShadow: "0 8px 32px rgba(0,0,0,0.6)",
            }}
          >
            <div style={{ fontSize: "11px", color: "#555", marginBottom: "4px", display: "flex", justifyContent: "space-between" }}>
              <span>Copartner noticed something</span>
              <span style={{ color: "#3B82F6" }}>{Math.round(sug.confidence * 100)}% confidence</span>
            </div>
            <div style={{ fontSize: "13px", color: "#ddd", lineHeight: 1.5, marginBottom: "10px" }}>
              {sug.text}
            </div>
            <div style={{ display: "flex", gap: "6px", justifyContent: "flex-end" }}>
              <button
                onClick={() => onDismiss(sug, true)}
                style={{
                  padding: "4px 8px", fontSize: "11px", color: "#555",
                  background: "transparent", border: "none", cursor: "pointer",
                }}
              >
                Never
              </button>
              <button
                onClick={() => onDismiss(sug, false)}
                style={{
                  padding: "4px 8px", fontSize: "11px", color: "#888",
                  background: "transparent", border: "1px solid #222",
                  borderRadius: "4px", cursor: "pointer",
                }}
              >
                Dismiss
              </button>
              <button
                onClick={() => onAccept(sug)}
                style={{
                  padding: "4px 12px", fontSize: "11px", color: "#000",
                  background: "#eee", border: "none",
                  borderRadius: "4px", cursor: "pointer", fontWeight: 600,
                }}
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
