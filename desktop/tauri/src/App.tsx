import { useState, useEffect, useRef } from "react";
import "./App.css";

type Status = "LISTENING" | "EXECUTING" | "CONNECTING" | "OFFLINE";

interface LogEntry {
  id: number;
  sender: string;
  text: string;
}

interface WsMessage {
  type: "log" | "status" | "tool";
  sender?: string;
  text?: string;
  value?: Status;
  name?: string;
  state?: "start" | "end";
}

const MAX_LOGS = 10;
const WS_URL   = "ws://localhost:8765";

function useClock(): string {
  const [time, setTime] = useState(() => new Date().toTimeString().slice(0, 8));
  useEffect(() => {
    const id = setInterval(() => setTime(new Date().toTimeString().slice(0, 8)), 1000);
    return () => clearInterval(id);
  }, []);
  return time;
}

function CoreSVG({ status }: { status: Status }) {
  const ticks = Array.from({ length: 36 }, (_, i) => {
    const a     = (i * 10 * Math.PI) / 180;
    const inner = i % 9 === 0 ? 123 : i % 3 === 0 ? 129 : 133;
    return {
      x1: Math.cos(a) * inner,   y1: Math.sin(a) * inner,
      x2: Math.cos(a) * 138.5,   y2: Math.sin(a) * 138.5,
      major: i % 9 === 0,
    };
  });

  return (
    <svg viewBox="-160 -160 320 320" className="core-svg" xmlns="http://www.w3.org/2000/svg">
      {/* Static guide tracks */}
      <circle r="130" fill="none" stroke="#0a4a5a" strokeWidth="0.5" />
      <circle r="90"  fill="none" stroke="#0a4a5a" strokeWidth="0.5" />
      <circle r="55"  fill="none" stroke="#0a4a5a" strokeWidth="0.5" />

      {/* Crosshair */}
      <line x1="-155" y1="0"    x2="-65" y2="0"    stroke="#00fff7" strokeWidth="0.5" strokeOpacity="0.3" />
      <line x1="65"   y1="0"    x2="155" y2="0"    stroke="#00fff7" strokeWidth="0.5" strokeOpacity="0.3" />
      <line x1="0"    y1="-155" x2="0"   y2="-65"  stroke="#00fff7" strokeWidth="0.5" strokeOpacity="0.3" />
      <line x1="0"    y1="65"   x2="0"   y2="155"  stroke="#00fff7" strokeWidth="0.5" strokeOpacity="0.3" />

      {/* Tick marks */}
      {ticks.map((t, i) => (
        <line key={i}
          x1={t.x1} y1={t.y1} x2={t.x2} y2={t.y2}
          stroke="#00fff7"
          strokeWidth={t.major ? "1.5" : "0.75"}
          strokeOpacity={t.major ? 0.5 : 0.22}
        />
      ))}

      {/* Corner HUD brackets */}
      <g stroke="#00fff7" strokeWidth="1.5" strokeOpacity="0.45" fill="none">
        <path d="M-150-150 h18 M-150-150 v18" />
        <path d="M150-150 h-18 M150-150 v18" />
        <path d="M-150 150 h18 M-150 150 v-18" />
        <path d="M150 150 h-18 M150 150 v-18" />
      </g>

      {/* Outer ring – rotates CW */}
      <g className="ring-outer">
        <circle r="130" fill="none" stroke="#00fff7" strokeWidth="1.5"
          strokeDasharray="72 20" strokeOpacity="0.7" />
      </g>

      {/* Middle ring – rotates CCW */}
      <g className="ring-middle">
        <circle r="90" fill="none" stroke="#00fff7" strokeWidth="1.5"
          strokeDasharray="48 14" strokeOpacity="0.75" />
      </g>

      {/* Inner ring – status-reactive */}
      <g className={`ring-inner ring-inner--${status.toLowerCase()}`}>
        <circle r="55" fill="none" stroke="#00fff7" strokeWidth="2"
          strokeDasharray="28 8" />
      </g>

      {/* Center */}
      <circle r="12" fill="none" stroke="#00fff7" strokeWidth="0.5"
        strokeOpacity="0.35" className="core-center-ring" />
      <circle r="5" fill="#00fff7" className="core-center-dot" />
    </svg>
  );
}

export default function App() {
  const [status,      setStatus]      = useState<Status>("OFFLINE");
  const [logs,        setLogs]        = useState<LogEntry[]>([]);
  const [activeTools, setActiveTools] = useState<string[]>([]);
  const idRef   = useRef(0);
  const logsEnd = useRef<HTMLDivElement>(null);
  const clock   = useClock();

  const currentTask = activeTools[activeTools.length - 1] ?? "";

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout>;
    let alive = true;

    function connect() {
      if (!alive) return;
      setStatus("CONNECTING");
      ws = new WebSocket(WS_URL);

      ws.onopen = () => setStatus("LISTENING");

      ws.onmessage = (e: MessageEvent<string>) => {
        let msg: WsMessage;
        try { msg = JSON.parse(e.data) as WsMessage; } catch { return; }

        if (msg.type === "log" && msg.text) {
          setLogs(prev =>
            [...prev, { id: idRef.current++, sender: msg.sender ?? "SYS", text: msg.text! }]
              .slice(-MAX_LOGS)
          );
        } else if (msg.type === "status" && msg.value) {
          setStatus(msg.value);
        } else if (msg.type === "tool" && msg.name) {
          const label = msg.name.replace(/_/g, " ").toUpperCase();
          if (msg.state === "start") {
            setActiveTools(prev => prev.includes(label) ? prev : [...prev, label]);
          } else if (msg.state === "end") {
            setActiveTools(prev => prev.filter(t => t !== label));
          }
        }
      };

      ws.onclose = () => {
        setStatus("OFFLINE");
        setActiveTools([]);
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
    logsEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  return (
    <div className="app">
      <div className="scanlines" aria-hidden="true" />

      {/* TOP BAR */}
      <header className="top-bar">
        <span className="logo">V.E.C.T.O.R.</span>
        <span className={`status-badge status-badge--${status.toLowerCase()}`}>
          ● {status}
        </span>
        <span className="clock">{clock}</span>
      </header>

      {/* MAIN CONTENT */}
      <main className="main-content">

        {/* LEFT: transcript */}
        <section className="panel panel--left">
          <div className="panel-label">/ TRANSCRIPT</div>
          <div className="transcript-list">
            {logs.length === 0 ? (
              <div className="transcript-empty">NO SIGNAL</div>
            ) : (
              logs.map((entry, i) => (
                <div
                  key={entry.id}
                  className={`transcript-entry transcript-entry--${entry.sender === "You" ? "you" : "vector"}`}
                  style={{ opacity: Math.max(0.25, 1 - (logs.length - 1 - i) * 0.08) }}
                >
                  <span className="transcript-sender">
                    {entry.sender === "You" ? "YOU" : "V.E.C.T.O.R."}
                  </span>
                  <span className="transcript-text">{entry.text}</span>
                </div>
              ))
            )}
            <div ref={logsEnd} />
          </div>
        </section>

        {/* CENTER: animated core */}
        <section className="core-area">
          <CoreSVG status={status} />
        </section>

        {/* RIGHT: active tools */}
        <section className="panel panel--right">
          <div className="panel-label">/ ACTIVE TOOLS</div>
          <div className="tools-list">
            {activeTools.length === 0 ? (
              <div className="tools-empty">IDLE</div>
            ) : (
              activeTools.map(tool => (
                <div key={tool} className="tool-entry">
                  <span className="tool-bullet">▶</span>
                  <span className="tool-name">{tool}</span>
                </div>
              ))
            )}
          </div>
        </section>

      </main>

      {/* BOTTOM BAR */}
      <footer className="bottom-bar">
        {currentTask && <span className="task-desc">▶ {currentTask}</span>}
      </footer>
    </div>
  );
}
