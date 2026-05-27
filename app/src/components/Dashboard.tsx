import { useState, useRef, useEffect } from "react";
import { motion } from "framer-motion";
import {
  Terminal, Database, Settings, ArrowUp,
  Minus, Loader2, Trash2,
  FolderOpen, ChevronDown, FileText,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Message, BudgetInfo, AmbientStatus } from "../hooks/useWebSocket";
import { setBarMode } from "../windowCommands";

type SidebarTab = "stream" | "memory" | "files" | "prefs";
type ConnState = "connecting" | "open" | "closed" | "error";

interface DashboardProps {
  messages: Message[];
  budget: BudgetInfo | null;
  ambientStatus: AmbientStatus;
  connState: ConnState;
  onSendMessage: (text: string) => void;
  onClearMessages: () => void;
  onMinimize: () => void;
  sendWs: (type: string, payload?: any) => void;
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

function MsgRow({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  const isError = msg.status === "error";

  return (
    <div style={{
      display: "flex",
      flexDirection: isUser ? "row-reverse" : "row",
      gap: "10px",
      maxWidth: "92%",
      alignSelf: isUser ? "flex-end" : "flex-start",
    }}>
      <div style={{
        width: 24,
        height: 24,
        borderRadius: "50%",
        background: isUser ? "#333" : "#eaff00",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: 9,
        fontWeight: 700,
        color: isUser ? "#aaa" : "#000",
        flexShrink: 0,
        marginTop: 2,
      }}>
        {isUser ? "H" : "A"}
      </div>
      <div style={{
        padding: "10px 14px",
        borderRadius: 10,
        background: isUser ? "#1a1a1a" : "#0e0e0e",
        border: `1px solid ${isError ? "#331a1a" : "#1a1a1a"}`,
        color: isError ? "#EF4444" : "#ccc",
        fontSize: 13,
        lineHeight: 1.5,
        maxWidth: "calc(100% - 40px)",
      }}>
        {isUser ? (
          <span>{msg.text}</span>
        ) : msg.status === "streaming" && !msg.text ? (
          <Loader2 size={14} style={{ animation: "spin 1.5s linear infinite" }} />
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.text}</ReactMarkdown>
        )}
      </div>
    </div>
  );
}

// ─── Memory View ─────────────────────────────────────────────────────────────
function MemoryView({ sendWs }: { sendWs: (type: string, payload?: any) => void }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<any[]>([]);

  useEffect(() => {
    const handler = (e: any) => {
      const data = e.detail?.results || [];
      setResults(data.map((r: any, i: number) => ({
        id: r.id || String(i),
        content: r.content || r.document || "",
        collection: r.collection || "unknown",
      })));
    };
    window.addEventListener("memory_data", handler);
    return () => window.removeEventListener("memory_data", handler);
  }, []);

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px" }}>
      <div style={{ display: "flex", gap: "8px", marginBottom: 16 }}>
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search memories..."
          onKeyDown={e => e.key === "Enter" && sendWs("get_memory", { query, n_results: 20 })}
          style={{
            flex: 1, background: "#0e0e0e", border: "1px solid #1a1a1a",
            borderRadius: 5, padding: "8px 12px", color: "#ccc", fontSize: 13, outline: "none"
          }}
        />
        <button
          onClick={() => sendWs("get_memory", { query, n_results: 20 })}
          style={{ background: "#eee", color: "#000", border: "none", borderRadius: 5, padding: "8px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
        >
          Search
        </button>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
        {results.map((mem: any) => (
          <div key={mem.id} style={{ padding: "10px 12px", borderRadius: 5 }}>
            <div style={{ fontSize: 12, color: "#bbb" }}>{mem.content}</div>
            <span style={{ fontSize: 10, color: "#3B82F6" }}>{mem.collection}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── File View ───────────────────────────────────────────────────────────────
function FileView({ sendWs }: { sendWs: (type: string, payload?: any) => void }) {
  const [entries, setEntries] = useState<any[]>([]);
  const [currentPath, setCurrentPath] = useState(".");
  const [fileContent, setFileContent] = useState<string | null>(null);

  useEffect(() => {
    sendWs("list_files", { path: currentPath, recursive: false });
  }, [currentPath, sendWs]);

  useEffect(() => {
    const handler = (e: any) => {
      const p = e.detail;
      if (p.content !== undefined) {
        setFileContent(p.content || "(empty)");
      } else if (p.entries) {
        setEntries(p.entries);
      }
    };
    window.addEventListener("file_data", handler);
    return () => window.removeEventListener("file_data", handler);
  }, []);

  const openFile = (name: string) => {
    const path = currentPath === "." ? name : `${currentPath}/${name}`;
    sendWs("read_file", { path });
  };

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "#666", marginBottom: 12 }}>
        <button
          onClick={() => {
            if (currentPath === ".") return;
            const parts = currentPath.split("/").filter(Boolean);
            parts.pop();
            setCurrentPath(parts.length === 0 ? "." : parts.join("/"));
            setFileContent(null);
          }}
          style={{ background: "transparent", border: "none", color: "#888", cursor: "pointer" }}
        >
          <ChevronDown size={14} style={{ transform: "rotate(90deg)" }} />
        </button>
        <span style={{ fontFamily: "monospace" }}>{currentPath}</span>
      </div>

      {fileContent !== null ? (
        <div>
          <button onClick={() => setFileContent(null)} style={{ background: "transparent", border: "none", color: "#555", cursor: "pointer", fontSize: 12, marginBottom: 8 }}>
            ← Back
          </button>
          <pre style={{ background: "#0a0a0a", border: "1px solid #1a1a1a", borderRadius: 6, padding: 12, fontSize: 12, fontFamily: "monospace", color: "#aaa", overflow: "auto", whiteSpace: "pre-wrap" }}>
            {fileContent}
          </pre>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "1px" }}>
          {entries.map((en: any) => (
            <div
              key={en.name}
              onClick={() => en.type === "dir" ? setCurrentPath(currentPath === "." ? en.name : `${currentPath}/${en.name}`) : openFile(en.name)}
              style={{ padding: "8px 12px", borderRadius: 5, cursor: "pointer", display: "flex", alignItems: "center", gap: 10 }}
            >
              {en.type === "dir" ? <FolderOpen size={14} color="#666" /> : <FileText size={14} color="#888" />}
              <span style={{ fontSize: 12, color: "#bbb" }}>{en.name}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Preferences View ────────────────────────────────────────────────────────
function PrefsView() {
  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px", color: "#888", fontSize: 13 }}>
      <p>Settings will be configurable here.</p>
      <p>Bar position, opacity, interruption thresholds, voice mode, budget limit.</p>
    </div>
  );
}

// ─── Main Dashboard ──────────────────────────────────────────────────────────
export default function Dashboard({
  messages,
  budget,
  ambientStatus,
  connState,
  onSendMessage,
  onClearMessages,
  onMinimize,
  sendWs,
}: DashboardProps) {
  const [activeTab, setActiveTab] = useState<SidebarTab>("stream");
  const feedRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight;
  }, [messages]);

  useEffect(() => {
    // Focus input when dashboard opens
    setTimeout(() => inputRef.current?.focus(), 100);
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const text = inputRef.current?.value.trim();
    if (!text) return;
    onSendMessage(text);
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: [0.25, 0.1, 0.25, 1] }}
      style={{
        width: "100%",
        height: "calc(100% - 40px)",
        display: "flex",
        background: "#050505",
        borderBottom: "1px solid #1a1a1a",
        overflow: "hidden",
      }}
    >
      {/* Sidebar */}
      <div style={{ width: 200, flexShrink: 0, background: "#080808", borderRight: "1px solid #1a1a1a", display: "flex", flexDirection: "column" }}>
        {/* Brand */}
        <div style={{ height: 44, display: "flex", alignItems: "center", padding: "0 14px", gap: 8, borderBottom: "1px solid #141414" }}>
          <div style={{ width: 16, height: 16, borderRadius: 4, background: "#eaff00", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 8, fontWeight: 800, color: "#000" }}>
            A
          </div>
          <span style={{ fontSize: 12, fontWeight: 600, color: "#ccc" }}>Copartner</span>
          <span style={{ fontSize: 10, color: "#444", marginLeft: "auto" }}>v2.0</span>
        </div>

        {/* Nav */}
        <nav style={{ padding: "8px 6px", display: "flex", flexDirection: "column", gap: "1px" }}>
          <NavBtn icon={<Terminal size={14} />} label="Stream" active={activeTab === "stream"} onClick={() => setActiveTab("stream")} />
          <NavBtn icon={<Database size={14} />} label="Memory" active={activeTab === "memory"} onClick={() => setActiveTab("memory")} />
          <NavBtn icon={<FolderOpen size={14} />} label="Files" active={activeTab === "files"} onClick={() => setActiveTab("files")} />
          <NavBtn icon={<Settings size={14} />} label="Settings" active={activeTab === "prefs"} onClick={() => setActiveTab("prefs")} />
        </nav>

        {/* Budget Widget */}
        {budget && (
          <div style={{ padding: "8px", borderTop: "1px solid #141414", marginTop: "auto" }}>
            <div style={{ fontSize: 10, fontWeight: 600, color: "#444", textTransform: "uppercase", letterSpacing: "0.06em", padding: "0 8px 6px" }}>Budget</div>
            <div style={{ padding: "8px", background: "#0e0e0e", borderRadius: 6, border: "1px solid #1a1a1a" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                <span style={{ fontSize: 11, color: "#666" }}>Today</span>
                <span style={{ fontSize: 11, color: "#ccc", fontWeight: 600 }}>{budget.cost_today}</span>
              </div>
              <div style={{ width: "100%", height: 4, background: "#1a1a1a", borderRadius: 2, overflow: "hidden" }}>
                <div style={{
                  width: budget.pct_used,
                  height: "100%",
                  background: parseFloat(budget.pct_used) > 80 ? "#EF4444" : parseFloat(budget.pct_used) > 50 ? "#F59E0B" : "#10B981",
                  borderRadius: 2,
                  transition: "width 0.3s",
                }} />
              </div>
              <div style={{ fontSize: 10, color: "#555", marginTop: 4, textAlign: "right" }}>
                {budget.tokens_used.toLocaleString()} / {budget.daily_limit.toLocaleString()} tokens
              </div>
            </div>
          </div>
        )}

        {/* Ambient Status */}
        {ambientStatus && Object.keys(ambientStatus).length > 0 && (
          <div style={{ padding: "8px", borderTop: "1px solid #141414" }}>
            <div style={{ fontSize: 10, fontWeight: 600, color: "#444", textTransform: "uppercase", letterSpacing: "0.06em", padding: "0 8px 6px" }}>Ambient</div>
            {ambientStatus.screen_observer && (
              <div style={{ fontSize: 10, color: "#555", padding: "2px 8px" }}>Screen: {ambientStatus.screen_observer}</div>
            )}
            {ambientStatus.ide_watcher && (
              <div style={{ fontSize: 10, color: "#555", padding: "2px 8px" }}>IDE: {ambientStatus.ide_watcher}</div>
            )}
            {ambientStatus.proactive_mode && (
              <div style={{ fontSize: 10, color: "#555", padding: "2px 8px" }}>Mode: {ambientStatus.proactive_mode}</div>
            )}
          </div>
        )}

        {/* User */}
        <div style={{ padding: "8px", borderTop: "1px solid #141414" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 8px", borderRadius: 5 }}>
            <div style={{ width: 22, height: 22, borderRadius: "50%", background: "#1a1a1a", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 9, color: "#666", fontWeight: 600 }}>H</div>
            <div>
              <div style={{ fontSize: 11, color: "#999" }}>Haziq</div>
              <div style={{ fontSize: 9, color: "#444" }}>Local</div>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {/* Header */}
        <div style={{
          height: 44, flexShrink: 0, borderBottom: "1px solid #1a1a1a",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "0 16px",
        }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: "#bbb" }}>
            {activeTab === "stream" && "Interaction Stream"}
            {activeTab === "memory" && "Memory Explorer"}
            {activeTab === "files" && "File Browser"}
            {activeTab === "prefs" && "Settings"}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {activeTab === "stream" && messages.length > 0 && (
              <button onClick={onClearMessages} style={{ background: "transparent", border: "none", color: "#444", cursor: "pointer", padding: 4, display: "flex" }} title="Clear conversation">
                <Trash2 size={13} />
              </button>
            )}
            <ConnPill state={connState} />
            <button
              onClick={() => { onMinimize(); setBarMode(); }}
              style={{ background: "transparent", border: "none", color: "#555", cursor: "pointer", padding: 4, display: "flex", borderRadius: 3 }}
            >
              <Minus size={13} />
            </button>
          </div>
        </div>

        {/* Content Area */}
        {activeTab === "stream" && (
          <>
            <div ref={feedRef} style={{ flex: 1, overflowY: "auto", padding: "16px 20px", display: "flex", flexDirection: "column", gap: 12 }}>
              {messages.length === 0 ? (
                <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", color: "#555" }}>
                  <div style={{ fontSize: 14, marginBottom: 4 }}>No messages yet.</div>
                  <div style={{ fontSize: 12 }}>Ask Copartner anything about your code.</div>
                </div>
              ) : (
                messages.map(msg => <MsgRow key={msg.id} msg={msg} />)
              )}
            </div>
            <div style={{ padding: "0 16px 12px", flexShrink: 0 }}>
              <form onSubmit={handleSubmit}>
                <div style={{
                  background: "#0e0e0e", border: "1px solid #1e1e1e", borderRadius: 8,
                  padding: "10px 12px", display: "flex", alignItems: "center", gap: 10,
                }}>
                  <input
                    ref={inputRef}
                    type="text"
                    placeholder="Message Copartner…"
                    style={{
                      flex: 1, background: "transparent", border: "none", outline: "none",
                      color: "#ccc", fontSize: 13, fontFamily: "var(--font-sans, system-ui, sans-serif)",
                    }}
                  />
                  <button type="submit" style={{
                    background: "#eee", color: "#000", border: "none", borderRadius: 5,
                    width: 26, height: 26, display: "flex", alignItems: "center", justifyContent: "center",
                    cursor: "pointer", flexShrink: 0,
                  }}>
                    <ArrowUp size={13} />
                  </button>
                </div>
              </form>
            </div>
          </>
        )}
        {activeTab === "memory" && <MemoryView sendWs={sendWs} />}
        {activeTab === "files" && <FileView sendWs={sendWs} />}
        {activeTab === "prefs" && <PrefsView />}
      </div>
    </motion.div>
  );
}

// ─── Nav Button ──────────────────────────────────────────────────────────────
function NavBtn({ icon, label, active, onClick }: { icon: React.ReactNode; label: string; active?: boolean; onClick?: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: "flex", alignItems: "center", gap: 8,
        padding: "7px 10px", borderRadius: 5,
        background: active ? "rgba(255,255,255,0.06)" : "transparent",
        border: "none", color: active ? "#ddd" : "#666",
        fontSize: 12, cursor: "pointer", textAlign: "left",
        transition: "all 0.15s",
      }}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}
