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
const S3       = Math.sqrt(3);

// ── helpers ────────────────────────────────────────────────────────────────

function useClock(): string {
  const [t, setT] = useState(() => new Date().toTimeString().slice(0, 8));
  useEffect(() => {
    const id = setInterval(() => setT(new Date().toTimeString().slice(0, 8)), 1000);
    return () => clearInterval(id);
  }, []);
  return t;
}

function poly(...verts: { x: number; y: number }[]): string {
  return verts.map(v => `${v.x.toFixed(2)},${v.y.toFixed(2)}`).join(" ");
}

// ── Arc-Reactor SVG ────────────────────────────────────────────────────────

function CoreSVG({ status }: { status: Status }) {
  const [hud, setHud] = useState({
    sr:   "48.0 kHz",
    br:   "320 kbps",
    gain: "+2.4 dB",
    seq:  "0x00A1",
  });

  useEffect(() => {
    const id = setInterval(() => {
      setHud({
        sr:   `${(47.8 + Math.random() * 0.4).toFixed(1)} kHz`,
        br:   `${316 + Math.floor(Math.random() * 8)} kbps`,
        gain: `+${(2.1 + Math.random() * 0.7).toFixed(1)} dB`,
        seq:  `0x${Math.floor(Math.random() * 0xffff)
                    .toString(16).toUpperCase().padStart(4, "0")}`,
      });
    }, 1200);
    return () => clearInterval(id);
  }, []);

  // 72 tick marks every 5°
  const ticks = Array.from({ length: 72 }, (_, i) => {
    const a     = (i * 5 * Math.PI) / 180;
    const major = i % 6 === 0;
    const mid   = !major && i % 2 === 0;
    const ro    = 184;
    const ri    = major ? 166 : mid ? 173 : 178;
    return {
      x1: Math.cos(a) * ri, y1: Math.sin(a) * ri,
      x2: Math.cos(a) * ro, y2: Math.sin(a) * ro,
      major, mid,
    };
  });

  // 6 connector spokes at 60° intervals
  const spokes = Array.from({ length: 6 }, (_, i) => {
    const a = (i * 60 * Math.PI) / 180;
    return {
      x1: Math.cos(a) * 102, y1: Math.sin(a) * 102,
      x2: Math.cos(a) * 157, y2: Math.sin(a) * 157,
    };
  });

  // Triforce geometry — equilateral triangle, circumradius R, pointing up
  const R  = 55;
  const tv = { x: 0,          y: -R      };   // top vertex
  const bv = { x: -R * S3 / 2, y: R / 2  };   // bottom-left vertex
  const cv = { x:  R * S3 / 2, y: R / 2  };   // bottom-right vertex

  // midpoints → corners of the three sub-triangles
  const ab = { x: (tv.x + bv.x) / 2, y: (tv.y + bv.y) / 2 }; // top ↔ BL
  const ac = { x: (tv.x + cv.x) / 2, y: (tv.y + cv.y) / 2 }; // top ↔ BR
  const bc = { x: (bv.x + cv.x) / 2, y: (bv.y + cv.y) / 2 }; // BL  ↔ BR

  return (
    <svg
      viewBox="-200 -200 400 400"
      className="core-svg"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        {/* radial background glow */}
        <radialGradient id="bg-grad" cx="50%" cy="50%" r="50%">
          <stop offset="0%"   stopColor="#00fff7" stopOpacity="0.08" />
          <stop offset="50%"  stopColor="#00fff7" stopOpacity="0.025" />
          <stop offset="100%" stopColor="#00fff7" stopOpacity="0" />
        </radialGradient>

        {/* soft glow filter */}
        <filter id="f-soft" x="-25%" y="-25%" width="150%" height="150%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="2.5" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>

        {/* strong glow filter (triforce + center dot) */}
        <filter id="f-strong" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="4.5" result="b1" />
          <feGaussianBlur in="SourceGraphic" stdDeviation="2"   result="b2" />
          <feMerge>
            <feMergeNode in="b1" />
            <feMergeNode in="b1" />
            <feMergeNode in="b2" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* ── ambient background glow ── */}
      <circle r="195" fill="url(#bg-grad)" />

      {/* ── HUD corner brackets ── */}
      <g
        stroke="#00fff7" strokeWidth="2" strokeLinecap="square"
        strokeOpacity="0.6" fill="none"
      >
        <path d="M-192-192 h30 M-192-192 v30" />
        <path d="M192-192 h-30 M192-192 v30" />
        <path d="M-192 192 h30 M-192 192 v-30" />
        <path d="M192 192 h-30 M192 192 v-30" />
      </g>

      {/* ── HUD data readouts ── */}
      <g
        className="hud-text"
        fontSize="6.5"
        fontFamily="'JetBrains Mono','Courier New',monospace"
      >
        {/* top-left */}
        <text x="-189" y="-164" fillOpacity="0.4">SAMPLERATE</text>
        <text x="-189" y="-153" fillOpacity="0.75" fontWeight="700">{hud.sr}</text>
        <text x="-189" y="-138" fillOpacity="0.4">GAIN</text>
        <text x="-189" y="-127" fillOpacity="0.75" fontWeight="700">{hud.gain}</text>

        {/* top-right */}
        <text x="189" y="-164" textAnchor="end" fillOpacity="0.4">BITRATE</text>
        <text x="189" y="-153" textAnchor="end" fillOpacity="0.75" fontWeight="700">{hud.br}</text>
        <text x="189" y="-138" textAnchor="end" fillOpacity="0.4">SEQ ID</text>
        <text x="189" y="-127" textAnchor="end" fillOpacity="0.75" fontWeight="700">{hud.seq}</text>
      </g>

      {/* ── 72 tick marks every 5° ── */}
      {ticks.map((t, i) => (
        <line
          key={i}
          x1={t.x1} y1={t.y1} x2={t.x2} y2={t.y2}
          stroke="#00fff7"
          strokeWidth={t.major ? "2" : t.mid ? "1" : "0.5"}
          strokeOpacity={t.major ? 0.9 : t.mid ? 0.45 : 0.18}
        />
      ))}

      {/* ── outer static hairline ring ── */}
      <circle r="185" fill="none" stroke="#00fff7" strokeWidth="0.5" strokeOpacity="0.22" />

      {/* ── Ring A — rotates CW ── */}
      <g className="ring-a" filter="url(#f-soft)">
        <circle
          r="163" fill="none" stroke="#00fff7"
          strokeWidth="2.5" strokeDasharray="54 14" strokeOpacity="0.9"
        />
      </g>

      {/* ── Ring B — rotates CCW ── */}
      <g className="ring-b" filter="url(#f-soft)">
        <circle
          r="128" fill="none" stroke="#00fff7"
          strokeWidth="2" strokeDasharray="36 10" strokeOpacity="0.85"
        />
      </g>

      {/* ── 6 connector spokes ── */}
      <g stroke="#00fff7" strokeOpacity="0.3" strokeWidth="0.75">
        {spokes.map((s, i) => (
          <g key={i}>
            <line x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2} />
            <circle cx={s.x2} cy={s.y2} r="3"   fill="#00fff7" fillOpacity="0.55" />
            <circle cx={s.x1} cy={s.y1} r="2"   fill="#00fff7" fillOpacity="0.4" />
          </g>
        ))}
      </g>

      {/* ── inner static ring ── */}
      <circle
        r="100" fill="none" stroke="#00fff7"
        strokeWidth="1.5" strokeOpacity="0.65"
        filter="url(#f-soft)"
      />

      {/* ── triforce ── */}
      <g filter="url(#f-strong)">
        <polygon points={poly(tv, ab, ac)} fill="#00fff7" fillOpacity="0.95" />
        <polygon points={poly(bv, ab, bc)} fill="#00fff7" fillOpacity="0.95" />
        <polygon points={poly(cv, ac, bc)} fill="#00fff7" fillOpacity="0.95" />
        {/* outer triangle outline */}
        <polygon
          points={poly(tv, bv, cv)}
          fill="none" stroke="#00fff7" strokeWidth="1" strokeOpacity="0.45"
        />
      </g>

      {/* ── center dark cap + pulsing core dot ── */}
      <circle r="25" fill="#010d1a" stroke="#00fff7" strokeWidth="1.5" strokeOpacity="0.55" />
      <circle r="10" fill="#00fff7" className="center-dot" filter="url(#f-strong)" />
    </svg>
  );
}

// ── App ────────────────────────────────────────────────────────────────────

export default function App() {
  const [status,      setStatus]      = useState<Status>("OFFLINE");
  const [logs,        setLogs]        = useState<LogEntry[]>([]);
  const [activeTools, setActiveTools] = useState<string[]>([]);
  const idRef   = useRef(0);
  const logsEnd = useRef<HTMLDivElement>(null);
  const clock   = useClock();

  const currentTask = activeTools[activeTools.length - 1] ?? "";

  // ── WebSocket (logic unchanged) ─────────────────────────────────────────
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
            [...prev, {
              id: idRef.current++,
              sender: msg.sender ?? "SYS",
              text: msg.text!,
            }].slice(-MAX_LOGS)
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

  // ── render ──────────────────────────────────────────────────────────────
  return (
    <div className="app">
      <div className="scanlines" aria-hidden="true" />

      {/* TOP BAR */}
      <header className="top-bar">
        <span className="logo">V.E.C.T.O.R.</span>
        <span className={`status-badge status-badge--${status.toLowerCase()}`}>
          ◉ {status}
        </span>
        <span className="clock">{clock}</span>
      </header>

      {/* MAIN */}
      <main className="main-content">

        {/* LEFT — transcript */}
        <aside className="panel panel--left">
          <div className="panel-header">/ TRANSCRIPT</div>
          <div className="transcript-scroll">
            {logs.length === 0 ? (
              <div className="placeholder">NO SIGNAL</div>
            ) : (
              logs.map((entry, i) => (
                <div
                  key={entry.id}
                  className={`msg msg--${entry.sender === "You" ? "you" : "vec"}`}
                  style={{ opacity: Math.max(0.2, 1 - (logs.length - 1 - i) * 0.09) }}
                >
                  <span className="msg-who">
                    {entry.sender === "You" ? "YOU" : "V.E.C.T.O.R."}
                  </span>
                  <span className="msg-body">{entry.text}</span>
                </div>
              ))
            )}
            <div ref={logsEnd} />
          </div>
        </aside>

        {/* CENTER — arc reactor */}
        <div className={`core-wrap core-wrap--${status.toLowerCase()}`}>
          <CoreSVG status={status} />
        </div>

        {/* RIGHT — active tools */}
        <aside className="panel panel--right">
          <div className="panel-header">/ ACTIVE TOOLS</div>
          <div className="tools-list">
            {activeTools.length === 0 ? (
              <div className="placeholder">IDLE</div>
            ) : (
              activeTools.map(tool => (
                <div key={tool} className="tool-row">
                  <span className="tool-arrow">▶</span>
                  <span className="tool-name">{tool}</span>
                </div>
              ))
            )}
          </div>
        </aside>

      </main>

      {/* BOTTOM BAR */}
      <footer className="bottom-bar">
        {currentTask && (
          <span className="task-text">▶ EXECUTING : {currentTask}</span>
        )}
      </footer>
    </div>
  );
}
