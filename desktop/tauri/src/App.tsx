import { useEffect, useRef, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import "./App.css";

type Status = "LISTENING" | "EXECUTING" | "CONNECTING" | "OFFLINE" | "BACKEND_ERROR";

const STATUS_LABEL: Record<Status, string> = {
  LISTENING: "LISTENING",
  EXECUTING: "EXECUTING",
  CONNECTING: "CONNECTING",
  OFFLINE: "OFFLINE",
  BACKEND_ERROR: "BACKEND ERROR",
};

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
const WS_URL = "ws://localhost:8765";
const S3 = Math.sqrt(3);

function useClock(): string {
  const [t, setT] = useState(() => new Date().toTimeString().slice(0, 8));

  useEffect(() => {
    const id = setInterval(() => setT(new Date().toTimeString().slice(0, 8)), 1000);
    return () => clearInterval(id);
  }, []);

  return t;
}

function useHudReadouts() {
  const [hud, setHud] = useState({
    sampleRate: "48.0 kHz",
    bitRate: "320 kbps",
    channels: "2.0 STEREO",
    phase: "SYNC 99.2%",
  });

  useEffect(() => {
    const id = setInterval(() => {
      setHud({
        sampleRate: `${(47.8 + Math.random() * 0.5).toFixed(1)} kHz`,
        bitRate: `${316 + Math.floor(Math.random() * 9)} kbps`,
        channels: Math.random() > 0.55 ? "2.0 STEREO" : "5.1 MATRIX",
        phase: `SYNC ${(97.6 + Math.random() * 2.3).toFixed(1)}%`,
      });
    }, 1300);

    return () => clearInterval(id);
  }, []);

  return hud;
}

function poly(...verts: { x: number; y: number }[]): string {
  return verts.map((v) => `${v.x.toFixed(2)},${v.y.toFixed(2)}`).join(" ");
}

function CoreSVG({ status }: { status: Status }) {
  const ticks = Array.from({ length: 72 }, (_, i) => {
    const angle = (i * 5 * Math.PI) / 180;
    const major = i % 6 === 0;
    const mid = !major && i % 2 === 0;
    const outerRadius = 184;
    const innerRadius = major ? 164 : mid ? 171 : 176;

    return {
      x1: Math.cos(angle) * innerRadius,
      y1: Math.sin(angle) * innerRadius,
      x2: Math.cos(angle) * outerRadius,
      y2: Math.sin(angle) * outerRadius,
      width: major ? 2.2 : mid ? 1.3 : 0.8,
      opacity: major ? 1 : mid ? 0.58 : 0.28,
    };
  });

  const spokes = Array.from({ length: 6 }, (_, i) => {
    const angle = (i * 60 * Math.PI) / 180;
    return {
      x1: Math.cos(angle) * 92,
      y1: Math.sin(angle) * 92,
      x2: Math.cos(angle) * 148,
      y2: Math.sin(angle) * 148,
    };
  });

  const outerShards = Array.from({ length: 12 }, (_, i) => {
    const angle = i * 30;
    return (
      <g key={angle} transform={`rotate(${angle})`}>
        <path
          d="M0 -173 L11 -162 L0 -151 L-11 -162 Z"
          className="reactor-accent-fill"
          fillOpacity="0.3"
        />
        <path
          d="M0 -166 L22 -154"
          className="reactor-accent-stroke"
          strokeWidth="1.2"
          strokeOpacity="0.55"
        />
        <path
          d="M0 -166 L-22 -154"
          className="reactor-accent-stroke"
          strokeWidth="1.2"
          strokeOpacity="0.55"
        />
      </g>
    );
  });

  const innerMarkers = Array.from({ length: 6 }, (_, i) => (
    <g key={i} transform={`rotate(${i * 60})`}>
      <path
        d="M0 -84 L8 -72 L0 -60 L-8 -72 Z"
        className="reactor-accent-fill"
        fillOpacity="0.5"
      />
    </g>
  ));

  const radius = 52;
  const top = { x: 0, y: -radius };
  const left = { x: (-radius * S3) / 2, y: radius / 2 };
  const right = { x: (radius * S3) / 2, y: radius / 2 };
  const topLeft = { x: (top.x + left.x) / 2, y: (top.y + left.y) / 2 };
  const topRight = { x: (top.x + right.x) / 2, y: (top.y + right.y) / 2 };
  const bottomMid = { x: (left.x + right.x) / 2, y: (left.y + right.y) / 2 };

  return (
    <svg
      viewBox="-210 -210 420 420"
      className={`core-svg core-svg--${status.toLowerCase()}`}
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <defs>
        <radialGradient id="reactor-bg" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#00fff7" stopOpacity="0.35" />
          <stop offset="28%" stopColor="#00fff7" stopOpacity="0.12" />
          <stop offset="100%" stopColor="#00fff7" stopOpacity="0" />
        </radialGradient>
        <filter id="reactor-soft" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="2.4" result="blurred" />
          <feMerge>
            <feMergeNode in="blurred" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id="reactor-strong" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="4.8" result="blurA" />
          <feGaussianBlur in="SourceGraphic" stdDeviation="2.1" result="blurB" />
          <feMerge>
            <feMergeNode in="blurA" />
            <feMergeNode in="blurA" />
            <feMergeNode in="blurB" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <circle r="198" fill="url(#reactor-bg)" />

      <g className="reactor-outer-rotor" filter="url(#reactor-soft)">
        <circle
          r="174"
          fill="none"
          className="reactor-primary-stroke"
          strokeWidth="2.4"
          strokeDasharray="46 10 12 18"
          strokeOpacity="0.92"
        />
        <circle
          r="166"
          fill="none"
          className="reactor-primary-stroke"
          strokeWidth="0.9"
          strokeDasharray="8 7"
          strokeOpacity="0.45"
        />
        {outerShards}
      </g>

      <g className="reactor-ticks" filter="url(#reactor-soft)">
        {ticks.map((tick, index) => (
          <line
            key={index}
            x1={tick.x1}
            y1={tick.y1}
            x2={tick.x2}
            y2={tick.y2}
            className="reactor-primary-stroke"
            strokeWidth={tick.width}
            strokeOpacity={tick.opacity}
          />
        ))}
      </g>

      <circle
        r="154"
        fill="none"
        className="reactor-primary-stroke"
        strokeWidth="0.8"
        strokeOpacity="0.34"
      />

      <g className="reactor-middle-ring" filter="url(#reactor-soft)">
        <circle
          r="138"
          fill="none"
          className="reactor-primary-stroke"
          strokeWidth="3"
          strokeDasharray="58 12 18 16"
          strokeOpacity="0.95"
        />
        <circle
          r="126"
          fill="none"
          className="reactor-primary-stroke"
          strokeWidth="1.1"
          strokeDasharray="4 9"
          strokeOpacity="0.58"
        />
      </g>

      <g className="reactor-spokes" filter="url(#reactor-soft)">
        {spokes.map((spoke, index) => (
          <g key={index}>
            <line
              x1={spoke.x1}
              y1={spoke.y1}
              x2={spoke.x2}
              y2={spoke.y2}
              className="reactor-primary-stroke"
              strokeWidth="1.4"
              strokeOpacity="0.42"
            />
            <circle
              cx={spoke.x1}
              cy={spoke.y1}
              r="3.2"
              className="reactor-accent-fill"
              fillOpacity="0.7"
            />
            <circle
              cx={spoke.x2}
              cy={spoke.y2}
              r="4"
              className="reactor-accent-fill"
              fillOpacity="0.42"
            />
          </g>
        ))}
      </g>

      <g className="reactor-inner-ring" filter="url(#reactor-soft)">
        <circle
          r="104"
          fill="none"
          className="reactor-primary-stroke"
          strokeWidth="2.2"
          strokeDasharray="24 8 12 14"
          strokeOpacity="0.92"
        />
        <circle
          r="88"
          fill="none"
          className="reactor-primary-stroke"
          strokeWidth="1"
          strokeDasharray="3 8"
          strokeOpacity="0.56"
        />
        {innerMarkers}
      </g>

      <circle
        r="69"
        fill="rgba(0, 255, 247, 0.06)"
        className="reactor-primary-stroke"
        strokeWidth="1.2"
        strokeOpacity="0.82"
        filter="url(#reactor-soft)"
      />

      <g className="reactor-core" filter="url(#reactor-strong)">
        <circle
          r="54"
          fill="rgba(0, 255, 247, 0.08)"
          className="reactor-primary-stroke"
          strokeWidth="1.6"
          strokeOpacity="0.95"
        />
        <polygon points={poly(top, topLeft, topRight)} className="reactor-core-fill" />
        <polygon points={poly(left, topLeft, bottomMid)} className="reactor-core-fill" />
        <polygon points={poly(right, topRight, bottomMid)} className="reactor-core-fill" />
        <polygon
          points={poly(top, left, right)}
          fill="none"
          className="reactor-primary-stroke"
          strokeWidth="1.2"
          strokeOpacity="0.65"
        />
        <circle r="12" className="reactor-core-dot" />
      </g>
    </svg>
  );
}

export default function App() {
  const [status, setStatus] = useState<Status>("OFFLINE");
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [activeTools, setActiveTools] = useState<string[]>([]);
  const idRef = useRef(0);
  const logsEnd = useRef<HTMLDivElement>(null);
  const clock = useClock();
  const hudReadouts = useHudReadouts();

  const currentTask = activeTools[activeTools.length - 1] ?? "";
  // BACKEND_ERROR reuses the "offline" visual style (red/inactive state).
  const statusClass = status === "BACKEND_ERROR" ? "offline" : status.toLowerCase();

  // Listen for backend-error events emitted by the Rust layer.
  useEffect(() => {
    let unlisten: (() => void) | undefined;
    listen<string>("backend-error", () => {
      setStatus("BACKEND_ERROR");
    }).then((fn) => {
      unlisten = fn;
    });
    return () => {
      unlisten?.();
    };
  }, []);

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
        try {
          msg = JSON.parse(e.data) as WsMessage;
        } catch {
          return;
        }

        if (msg.type === "log" && msg.text) {
          setLogs((prev) =>
            [
              ...prev,
              {
                id: idRef.current++,
                sender: msg.sender ?? "SYS",
                text: msg.text!,
              },
            ].slice(-MAX_LOGS),
          );
        } else if (msg.type === "status" && msg.value) {
          setStatus(msg.value);
        } else if (msg.type === "tool" && msg.name) {
          const label = msg.name.replace(/_/g, " ").toUpperCase();
          if (msg.state === "start") {
            setActiveTools((prev) => (prev.includes(label) ? prev : [...prev, label]));
          } else if (msg.state === "end") {
            setActiveTools((prev) => prev.filter((t) => t !== label));
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

    // 2-second delay: give Python backend time to start before connecting.
    const initTimer = setTimeout(connect, 2000);
    return () => {
      alive = false;
      clearTimeout(initTimer);
      clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, []);

  useEffect(() => {
    logsEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  return (
    <div className={`app app--${statusClass}`}>
      <div className="scanlines" aria-hidden="true" />

      <header className="top-bar">
        <div className="logo">V.E.C.T.O.R.</div>
        <div className={`status-pill status-pill--${statusClass}`}>
          <span className="status-pill__label">◉ STATUS</span>
          <span className="status-pill__value">{STATUS_LABEL[status]}</span>
        </div>
        <time className="clock">{clock}</time>
      </header>

      <main className="hud-layout">
        <aside className="panel panel--transcript">
          <div className="panel__header">/ TRANSCRIPT</div>
          <div className="transcript-feed">
            {logs.length === 0 ? (
              <div className="panel__empty">NO SIGNAL</div>
            ) : (
              logs.map((entry, index) => {
                const fade =
                  logs.length === 1 ? 1 : 0.2 + (index / (logs.length - 1)) * 0.8;

                return (
                  <article
                    key={entry.id}
                    className={`msg msg--${entry.sender === "You" ? "you" : "vector"}`}
                    style={{ opacity: fade }}
                  >
                    <span className="msg__sender">
                      {entry.sender === "You" ? "YOU" : "V.E.C.T.O.R."}
                    </span>
                    <span className="msg__text">{entry.text}</span>
                  </article>
                );
              })
            )}
            <div ref={logsEnd} />
          </div>
        </aside>

        <section className="reactor-stage">
          <div className={`core-chamber core-chamber--${statusClass}`}>
            <span className="core-corner core-corner--tl">┌</span>
            <span className="core-corner core-corner--tr">┐</span>
            <span className="core-corner core-corner--bl">└</span>
            <span className="core-corner core-corner--br">┘</span>

            <div className="core-readout core-readout--left">
              <span className="core-readout__label">SAMPLERATE</span>
              <span className="core-readout__value">{hudReadouts.sampleRate}</span>
              <span className="core-readout__label">CHANNELS</span>
              <span className="core-readout__value">{hudReadouts.channels}</span>
            </div>

            <div className="core-readout core-readout--right">
              <span className="core-readout__label">BITRATE</span>
              <span className="core-readout__value">{hudReadouts.bitRate}</span>
              <span className="core-readout__label">LINK PHASE</span>
              <span className="core-readout__value">{hudReadouts.phase}</span>
            </div>

            <div className="core-readout core-readout--lower-left">
              <span className="core-readout__label">MODE</span>
              <span className="core-readout__value">ARC // {status}</span>
            </div>

            <div className="core-readout core-readout--lower-right">
              <span className="core-readout__label">VECTOR CORE</span>
              <span className="core-readout__value">EMISSIVE CYAN</span>
            </div>

            <CoreSVG status={status} />
          </div>
        </section>

        <aside className="panel panel--tools">
          <div className="panel__header">/ ACTIVE TOOLS</div>
          <div className="tools-feed">
            {activeTools.length === 0 ? (
              <div className="panel__empty">STANDBY</div>
            ) : (
              activeTools.map((tool) => (
                <div key={tool} className="tool-row">
                  <span className="tool-row__arrow">▶</span>
                  <span className="tool-row__name">{tool}</span>
                </div>
              ))
            )}
          </div>
        </aside>
      </main>

      <footer className="bottom-bar">
        <div className="bottom-bar__scan" aria-hidden="true" />
        {status === "EXECUTING" && currentTask ? (
          <div className="task-text">CURRENT TASK // {currentTask}</div>
        ) : null}
      </footer>
    </div>
  );
}
