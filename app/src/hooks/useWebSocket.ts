import { useState, useEffect, useRef, useCallback } from "react";

export type ConnState = "connecting" | "open" | "closed" | "error";
export type AIState = "idle" | "watching" | "thinking" | "urgent";

export interface AmbientStatus {
  status?: string;
  screen_observer?: string;
  ide_watcher?: string;
  proactive_mode?: string;
  last_file_event?: string;
}

export interface BudgetInfo {
  date: string;
  tokens_used: number;
  daily_limit: number;
  pct_used: string;
  cost_today: string;
  by_model: Record<string, number>;
  status: string;
}

export interface Suggestion {
  id: string;
  text: string;
  action: string;
  confidence: number;
}

export interface ToolExec {
  tag: string;
  status: "start" | "end";
  content?: string;
  result_preview?: string;
}

export interface Message {
  id: string;
  role: "user" | "agent";
  text: string;
  timestamp: Date;
  status: "streaming" | "complete" | "error";
  tools?: ToolExec[];
}

const WS_URL = "ws://127.0.0.1:8765";
const STORAGE_KEY = "copartner_chat_v2";

function saveMessages(msgs: Message[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(msgs.map(m => ({
      ...m, timestamp: m.timestamp.toISOString()
    }))));
  } catch (_) {}
}

function loadMessages(): Message[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    return JSON.parse(raw).map((m: any) => ({
      ...m, timestamp: new Date(m.timestamp)
    }));
  } catch (_) { return []; }
}

let msgId = 0;

export function useCopartnerWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const [connState, setConnState] = useState<ConnState>("connecting");
  const [aiState, setAiState] = useState<AIState>("idle");
  const [statusText, setStatusText] = useState("Copartner ready");
  const [errorCount, setErrorCount] = useState(0);
  const [messages, setMessages] = useState<Message[]>(loadMessages);
  const [budget, setBudget] = useState<BudgetInfo | null>(null);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [ambientStatus, setAmbientStatus] = useState<AmbientStatus>({});
  const pendingIdRef = useRef<string | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    setConnState("connecting");
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnState("open");
      ws.send(JSON.stringify({ type: "ping" }));
    };

    ws.onclose = () => {
      setConnState("closed");
      wsRef.current = null;
      // Auto-reconnect
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      reconnectTimer.current = setTimeout(connect, 2000);
    };

    ws.onerror = () => {
      setConnState("error");
    };

    ws.onmessage = (ev) => {
      try {
        const { type, payload: p } = JSON.parse(ev.data);
        switch (type) {
          case "pong": break;
          case "stream_chunk": {
            const pid = pendingIdRef.current;
            const chunk = p.chunk ?? p.text ?? "";
            if (pid && chunk) {
              setMessages(prev => prev.map(m =>
                m.id === pid ? { ...m, text: m.text + chunk } : m
              ));
            }
            setAiState("thinking");
            break;
          }
          case "tool_event": {
            const pid = pendingIdRef.current;
            if (!pid) break;
            setMessages(prev => {
              const idx = prev.findIndex(m => m.id === pid);
              if (idx === -1) return prev;
              const msg = prev[idx];
              const tools = [...(msg.tools || [])];
              if (p.status === "start") {
                tools.push({ tag: p.tag, status: "start", content: p.content });
              } else {
                const tidx = tools.findIndex(t => t.tag === p.tag && t.status === "start");
                if (tidx !== -1) {
                  tools[tidx] = { ...tools[tidx], status: "end", result_preview: p.result_preview };
                }
              }
              const updated = [...prev];
              updated[idx] = { ...msg, tools };
              return updated;
            });
            break;
          }
          case "final_answer": {
            const pid = pendingIdRef.current;
            if (pid) {
              setMessages(prev => prev.map(m =>
                m.id === pid ? { ...m, text: p.text, status: "complete" } : m
              ));
              pendingIdRef.current = null;
            }
            setAiState("idle");
            setStatusText("Analysis complete");
            break;
          }
          case "error": {
            const pid = pendingIdRef.current;
            if (pid) {
              setMessages(prev => prev.map(m =>
                m.id === pid ? { ...m, text: `**Error:** ${p.message}`, status: "error" } : m
              ));
              pendingIdRef.current = null;
            }
            setAiState("idle");
            break;
          }
          case "state_update": {
            if (p.ambient) setAmbientStatus(prev => ({ ...prev, ...p.ambient }));
            if (p.status) setStatusText(p.status);
            break;
          }
          case "token_usage": {
            setBudget(p);
            break;
          }
          case "proactive_suggestion": {
            setSuggestions(prev => [...prev, { id: p.id, text: p.text, action: p.action, confidence: p.confidence }]);
            setAiState("thinking");
            setStatusText(p.text);
            break;
          }
          case "urgency_alert": {
            setAiState("urgent");
            setStatusText(p.message);
            setErrorCount(prev => prev + 1);
            break;
          }
          case "ambient_status": {
            setAiState(p.state || "idle");
            setStatusText(p.message || "Copartner ready");
            if (p.error_count !== undefined) setErrorCount(p.error_count);
            break;
          }
          case "system_stats": {
            if (p.budget) setBudget(p.budget);
            break;
          }
        }
      } catch (e) {
        console.error("WS parse error:", e);
      }
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  useEffect(() => {
    saveMessages(messages);
  }, [messages]);

  const sendQuery = useCallback((text: string) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      alert("Copartner brain is not connected.");
      return;
    }

    const userMsg: Message = {
      id: String(++msgId), role: "user", text: text.trim(),
      timestamp: new Date(), status: "complete",
    };
    setMessages(prev => [...prev, userMsg]);

    const pendingId = String(++msgId);
    pendingIdRef.current = pendingId;
    setMessages(prev => [...prev, {
      id: pendingId, role: "agent", text: "",
      timestamp: new Date(), status: "streaming",
    }]);

    ws.send(JSON.stringify({ type: "query", payload: { text: text.trim() } }));
  }, []);

  const sendWs = useCallback((type: string, payload?: any) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type, payload: payload || {} }));
    }
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  const dismissSuggestion = useCallback((id: string) => {
    sendWs("suggestion_dismiss", { id });
    setSuggestions(prev => prev.filter(s => s.id !== id));
  }, [sendWs]);

  return {
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
  };
}
