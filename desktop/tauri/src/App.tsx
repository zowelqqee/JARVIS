import { useState, useEffect, useRef } from "react";
import "./App.css";

type Role = "user" | "assistant" | "system";
type VectorState =
  | "connecting"
  | "listening"
  | "thinking"
  | "responding"
  | "executing"
  | "error"
  | "disconnected";

interface LogEntry {
  id: number;
  text: string;
  role: Role;
}

interface WsMessage {
  type: "log" | "status";
  text?: string;
  role?: Role;
  state?: VectorState;
  detail?: string;
}

const STATUS_LABEL: Record<VectorState, string> = {
  connecting:   "CONNECTING",
  listening:    "LISTENING",
  thinking:     "PROCESSING",
  responding:   "RESPONDING",
  executing:    "EXECUTING",
  error:        "ERROR",
  disconnected: "OFFLINE",
};

const STATUS_CLASS: Record<VectorState, string> = {
  listening:    "status--ok",
  responding:   "status--active",
  thinking:     "status--active",
  executing:    "status--exec",
  error:        "status--error",
  disconnected: "status--off",
  connecting:   "status--dim",
};

const WS_URL = "ws://localhost:8765";

export default function App() {
  const [vectorState, setVectorState] = useState<VectorState>("disconnected");
  const [detail, setDetail] = useState("");
  const [wsConnected, setWsConnected] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const idRef = useRef(0);
  const logsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout>;
    let alive = true;

    function connect() {
      if (!alive) return;
      ws = new WebSocket(WS_URL);

      ws.onopen = () => {
        setWsConnected(true);
        console.log("[V.E.C.T.O.R.] WS connected");
      };

      ws.onmessage = (e: MessageEvent<string>) => {
        let msg: WsMessage;
        try {
          msg = JSON.parse(e.data) as WsMessage;
        } catch {
          return;
        }
        if (msg.type === "log" && msg.text) {
          setLogs((prev) => [
            ...prev,
            { id: idRef.current++, text: msg.text!, role: msg.role ?? "system" },
          ]);
        } else if (msg.type === "status" && msg.state) {
          setVectorState(msg.state);
          setDetail(msg.detail ?? "");
        }
      };

      ws.onclose = () => {
        setWsConnected(false);
        setVectorState("disconnected");
        if (alive) reconnectTimer = setTimeout(connect, 3000);
      };

      ws.onerror = () => ws?.close();
    }

    connect();

    return () => {
      alive = false;
      clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, []);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const statusLabel =
    vectorState === "executing" && detail
      ? `▶ ${detail.replace(/_/g, " ").toUpperCase()}`
      : vectorState === "error" && detail
      ? `ERROR: ${detail}`
      : STATUS_LABEL[vectorState];

  return (
    <div className="app">
      <header className="header">
        <span className="header-title">V.E.C.T.O.R.</span>
        <span className="header-sub">
          Vigilance Engine, Command Tracking and Operational Response
        </span>
        <span className={`ws-badge ${wsConnected ? "ws-badge--on" : "ws-badge--off"}`}>
          {wsConnected ? "◉ WS" : "○ WS"}
        </span>
      </header>

      <div className={`status-bar ${STATUS_CLASS[vectorState]}`}>
        <span className="status-dot">●</span>
        <span>{statusLabel}</span>
      </div>

      <div className="log-area">
        {logs.length === 0 ? (
          <div className="log-empty">
            {wsConnected ? "● WAITING FOR INPUT" : "○ BACKEND OFFLINE"}
          </div>
        ) : (
          logs.map((entry) => (
            <div key={entry.id} className={`log-line log-line--${entry.role}`}>
              {entry.text}
            </div>
          ))
        )}
        <div ref={logsEndRef} />
      </div>

      <footer className="footer">
        FatihMakes Industries&nbsp;·&nbsp;CLASSIFIED&nbsp;·&nbsp;V.E.C.T.O.R.
      </footer>
    </div>
  );
}
