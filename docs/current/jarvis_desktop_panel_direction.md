# Goal

Reframe the JARVIS desktop client from a chat-window application into a compact,
always-visible control panel. JARVIS executes actions in the real operating system UI.
The desktop client exists only to surface state, confirm intent, and receive brief input —
not to replay the world as a chat log.

---

# What Is Wrong With The Current Desktop UI

1. **Window is too large.** 1100×760px default, 900×600px minimum. This is a full application
   footprint, not a control surface. It competes with the workspace it is supposed to support.

2. **Chat view is the dominant element.** The `ConversationView` takes 71% of width and all
   available vertical stretch. This makes JARVIS look and feel like a messaging app.

3. **Transcript is the primary information.** The conversation list shows everything that has
   ever been said. Most of that is noise once an action is underway. Users do not need to scroll
   through chat history to understand what JARVIS is doing right now.

4. **Status panel is secondary.** The `StatusPanel` lives in a 29%-wide right column. It contains
   the most operationally useful information (runtime state, current step, blocked reason,
   pending prompt) but is visually subordinate to the chat list.

5. **Composer is oversized.** A 96px-minimum multi-line `QPlainTextEdit` is sized for long
   messages. JARVIS commands are short. The input area consumes real estate that should belong
   to status.

6. **Theme is wrong.** Warm off-white (`#f3ede2`), rounded 20px cards, Segoe UI at 10pt. This
   is a consumer productivity aesthetic. It does not match the cinematic-system feel the product
   requires, and does not signal that the user is operating a capable, autonomous agent.

7. **No visual hierarchy between runtime state and history.** Current state (what is happening
   now) and past state (what happened before) are presented at equal weight. The user cannot
   immediately see what JARVIS is doing without reading the transcript.

8. **No compact/floating mode.** The window is always full-size and desktop-bound. There is no
   way to keep JARVIS present without it occupying a significant screen region.

---

# What To Keep

- **`StatusViewModel` data model.** The fields `runtime_state`, `command_summary`,
  `current_step`, `blocked_reason`, `pending_prompt`, `can_cancel`, `speech_enabled` are
  exactly the right information surface. Keep the model, change the presentation.

- **`PendingPromptViewModel`.** Confirmation and clarification prompts are a core product
  feature. The data contract is correct.

- **`ConversationController` wiring pattern.** Signals flow up (`submitted`, `speech_toggled`),
  state flows down (snapshot rendering). This is clean and should be preserved.

- **`EngineFacade` as the desktop boundary.** `submit_text()` → `snapshot()` is the right
  contract. Do not change this interface.

- **`BackendSessionService` history tracking.** Short-term history is necessary for re-render
  on state change. Keep it; reduce how much of it is shown by default.

- **`presenters.py` adapter pattern.** Translating core visibility dicts into typed view models
  is the right abstraction. Keep the pipeline, extend it for panel-specific fields.

- **Explicit submission model.** The user sends input intentionally. Do not switch to
  auto-submit on keypress. The send action should remain deliberate.

---

# What To Remove Or Reduce

| Element | Action | Reason |
|---------|--------|--------|
| `ConversationView` as primary pane | Reduce to a collapsible secondary section or a narrow scrolling log strip | It is not the primary information for a control panel |
| Transcript always visible | Replace with a single "last exchange" display; full log accessible on demand | Reduces visual noise; current state is what matters |
| `ComposerWidget` subtitle ("Write a request and press Send…") | Remove | Wastes space; the input field is self-evident |
| Multi-line `QPlainTextEdit` as default input | Replace with a single-line compact input bar; expand only when needed | Commands are short; the full text editor signals the wrong interaction model |
| Warm light theme (`#f3ede2`, rounded 20px cards, Segoe UI) | Replace entirely with dark compact theme | Does not match product feel |
| Window default size 1100×760 | Shrink to ~420×560 or a narrow vertical strip | Panel must not compete with the workspace |
| Speech status taking three form rows | Consolidate to a single icon + status chip | Audio state is secondary metadata, not three-field form data |
| Card titles at 21pt bold ("Conversation", "Status", "Ask JARVIS") | Remove or reduce to 9–10pt section labels | Section headers at title size dominate the panel; labels should be minimal |
| `ShellWidgets` 5:2 horizontal split | Remove the horizontal split entirely | Panel-first means vertical layout, single column |
| Qt status bar ("Starting JARVIS…") | Remove | Redundant with the status panel; adds OS-chrome noise |

---

# Panel-First UI Direction

The desktop client becomes a **single vertical panel** — narrow, always available, and focused
on the current moment.

Layout direction: **top to bottom, single column.**

```
┌─────────────────────────┐
│  [●] JARVIS   [–] [×]   │  ← compact titlebar, draggable
├─────────────────────────┤
│  MODE    RUNTIME STATE  │  ← state row: mode chip + status chip
├─────────────────────────┤
│                         │
│  CURRENT STEP / LAST    │  ← primary display: what is happening now
│  UNDERSTOOD ACTION      │     or what was just understood
│                         │
├─────────────────────────┤
│  [CONFIRM]   [CANCEL]   │  ← conditional: only shown when pending prompt exists
│  "Open Finder and…"     │
├─────────────────────────┤
│  ▸ last message         │  ← condensed: last assistant reply / last user input
│  ▸ …                    │     (1–3 lines, not a full transcript)
├─────────────────────────┤
│  [input bar _________ ▶]│  ← single-line input, send on Enter or button
│  [🎙] [⊕]               │  ← mic toggle, optional extras
└─────────────────────────┘
```

The panel floats above the workspace or docks to a screen edge. It never covers the region
where JARVIS is actively working (opened windows, focused applications).

---

# Minimum Panel Sections

These are the only sections required at launch. Nothing else.

## Layout Contract

### Section Order (top to bottom, fixed)

```
1. Titlebar          — always visible
2. State Row         — always visible
3. Current Action    — always visible
4. Prompt Zone       — conditional (pending_prompt only)
5. Last Exchange     — always visible
6. Input Bar         — always visible
```

No section may reorder or be hidden except Prompt Zone.

---

### Visibility Rules

| # | Section | Always visible | Conditional |
|---|---------|---------------|-------------|
| 1 | Titlebar | yes | — |
| 2 | State Row | yes | — |
| 3 | Current Action | yes | — |
| 4 | Prompt Zone | — | only when `pending_prompt` is not None |
| 5 | Last Exchange | yes | — |
| 6 | Input Bar | yes | — |

When Prompt Zone is hidden, the space it would occupy collapses fully.
No placeholder, no empty box, no separator line.

---

### Section Content By State

| State | State Row chips | Current Action | Prompt Zone | Last Exchange | Input Bar |
|-------|----------------|----------------|-------------|---------------|-----------|
| **idle** | `IDLE` · `IDLE` | Last completion result, or "Ready." if none | hidden | Last user + JARVIS pair, dimmed | enabled |
| **listening** | `IDLE` · `LISTENING` | "Listening…" | hidden | Last pair, dimmed | disabled (mic active) |
| **thinking** | mode chip · `PARSING` | "Processing…" | hidden | Last pair, dimmed | disabled |
| **executing** | `COMMAND` · `EXECUTING` | `command_summary` — `current_step` | hidden | Last pair, dimmed | disabled |
| **awaiting_clarification** | `COMMAND` · `WAITING` | `blocked_reason` (why it stopped) | shown: clarification question + text input field + SEND | Last pair, dimmed | disabled (Prompt Zone owns input) |
| **awaiting_confirmation** | `COMMAND` · `WAITING` | `command_summary` — what is about to happen | shown: confirmation message + CONFIRM + CANCEL | Last pair, dimmed | disabled (Prompt Zone owns input) |
| **answering** | `QUESTION` · `ANSWERING` | Answer text (streaming or complete) | hidden | Last pair, updating | disabled |
| **failed** | mode chip · `ERROR` | `failure_message` | hidden | Last pair with error entry visible | enabled (user can retry) |

**Rules for "disabled" input bar:** field is visually muted (opacity 0.4), not hidden.
Placeholder text changes to match state (e.g. "JARVIS is executing…", "Listening…").

---

### Width Contract

| Property | Value |
|----------|-------|
| Minimum width | 360px |
| Preferred width | 400px |
| Maximum width | 440px (hard cap, never wider) |
| Height | 520px default, resizable vertically down to 420px |

All section content must wrap or truncate within the panel width.
No horizontal scroll. No content overflow.
Long strings (file paths, commands) truncate with `…` at the end.

---

### Prompt Zone Behaviour When No Prompt Is Pending

The Prompt Zone does not exist in the layout when `pending_prompt` is None.
It is not collapsed with zero height — it is removed from the widget tree entirely.
The sections above and below it are adjacent with no gap.
When a prompt arrives, the zone is inserted between Current Action and Last Exchange,
pushing Last Exchange and Input Bar down. The transition has no animation.

---

### 1. Titlebar
- Height: 32px fixed
- Content: `[●] JARVIS` left-aligned, `[–] [×]` right-aligned
- Drag region: full titlebar width
- The `●` dot reflects runtime state color (accent = active, muted = idle)

### 2. State Row
- Height: 28px fixed
- Two chips side by side, left-aligned, with 8px gap
- Left chip: mode — `COMMAND` / `QUESTION` / `IDLE`
- Right chip: runtime state — `IDLE` / `LISTENING` / `PARSING` / `EXECUTING` / `WAITING` / `ANSWERING` / `ERROR`
- Chips are read-only labels, not buttons

### 3. Current Action Display
- Height: min 48px, expands to max 3 lines before truncating
- Primary font weight, prominent
- Maps to: `command_summary` + `current_step` during execution; `blocked_reason` when waiting;
  `failure_message` on error; last `completion_result` or "Ready." when idle
- Text truncates to 3 lines with `…`; no scrolling within this section

### 4. Prompt Zone (conditional)
- Rendered only when `pending_prompt` is not None
- **Confirmation kind**: shows `pending_prompt.message` + `[CONFIRM]` + `[CANCEL]` buttons
- **Clarification kind**: shows `pending_prompt.message` + single-line text input + `[SEND]` button
- The text input inside Prompt Zone receives focus automatically when zone appears
- `[CANCEL]` always present; dismisses prompt and unblocks the engine
- Section has a 1px accent-color border on the left edge to draw attention

### 5. Last Exchange Strip
- Height: fixed 2-row display (last user input line + last JARVIS response line)
- Smaller font (secondary text color, 10pt)
- Not scrollable inline; clicking the strip opens a separate full-log overlay (out of scope for now)
- If no exchange yet: single dimmed line — "No previous exchange."
- Content never overflows: each line truncates with `…`

### 6. Input Bar
- Height: 36px fixed (single-line); expands to max 72px if content exceeds one line
- Single-line `QLineEdit`; auto-expands to two lines max on overflow
- Enter or `[▶]` button submits
- Mic toggle `[🎙]` on the left of the field
- Placeholder text is state-dependent (see state table above)
- Disabled states: field opacity 0.4, buttons non-interactive

---

# Visual Style Direction

**Target aesthetic**: dark compact control surface. Cinematic-system, not neon sci-fi.

| Property | Value |
|----------|-------|
| Background | `#0d0d0f` (near-black) |
| Surface (panel card) | `#111215` (dark charcoal) |
| Border | `#1e2028` (subtle, 1px) |
| Primary text | `#e8eaed` (cool off-white) |
| Secondary text | `#6b7280` (muted grey) |
| Accent | `#3b82f6` (system blue) or `#00d4aa` (teal-cyan) — one only |
| State: executing | accent color, subtle pulse animation (opacity only, no movement) |
| State: waiting | amber `#f59e0b` chip |
| State: error | `#ef4444` chip |
| State: idle | `#374151` muted chip |
| Font | `JetBrains Mono` or `SF Mono` / `Consolas` — monospace, 11–12pt |
| Corner radius | 6–8px (tight, not rounded-card) |
| Panel width | 380–440px fixed |
| Panel height | 520–580px default, resizable vertically |
| Shadows | Drop shadow on panel float: `0 8px 32px rgba(0,0,0,0.6)` |
| Window chrome | Frameless or minimal: custom titlebar, drag region only |
| Borders | Hairline, no thick borders, no glows |
| Icons | Phosphor or Lucide icon set — monoline, consistent weight |

## Visual Anti-Goals

The following are banned. If a design choice resembles any of these, reject it.

| Anti-goal | Banned pattern |
|-----------|----------------|
| Cheesy sci-fi | Scanning line animations, CRT flicker, fake hologram effects |
| Neon clutter | Purple/pink/cyan gradients, color-cycling text, rainbow borders |
| Oversized presence | Pulsing orbs, animated blobs, large glowing rings around state |
| Glassmorphism | Frosted blur panels, translucent layered cards |
| Consumer chat | Rounded 20px+ card borders, warm off-white backgrounds, large send buttons |
| Dashboard creep | Progress bars for everything, charts, meters, percentage readouts |
| Loud errors | Full-screen error modals, red background flash, shaking animations |
| Overcrowded chrome | Multiple toolbars, icon rows, persistent menu items visible at all times |

One animation is permitted: a **slow opacity pulse** (0.6 → 1.0 → 0.6, 2s cycle) on the
State Row chip while `runtime_state` is `EXECUTING` or `PARSING`. Nothing else moves.

---

# How The Panel Relates To Real Desktop Actions

JARVIS actions happen in the real OS: windows open, files move, apps launch, focus shifts.
The panel's role is not to simulate or mirror this — it is to narrate and control it.

```
Real OS (ground truth)        JARVIS Panel (control surface)
──────────────────────        ──────────────────────────────
Finder opens                  "STEP: Open Finder"     (label)
File gets moved                "STEP: Move ~/Downloads/…"
Focus shifts to browser        "STEP: Focus Safari"
[user sees these happen]       [panel echoes the step]
                               Pending: "Save to Desktop?" [CONFIRM] [CANCEL]
Browser loads URL              [panel shows EXECUTING]
Done                           "RESULT: Done" → panel goes IDLE
```

The panel is a **running commentary and control point** — not a simulation.
The user's eye should stay on their real screen, glancing at the panel only to confirm or cancel.

Design consequences:
- The panel must **never block the work region**
- The panel must not **require the user to look at it** to understand what is happening
- The panel **must be readable in a glance** — state row + current action is a 1-second read
- Confirmation prompts must be **visible enough to catch attention** (accent border, slight elevation)
  without requiring the user to switch focus completely

---

# Fit With JARVIS Core And Future ARIA Client

The current architecture already supports this direction cleanly:

```
JARVIS Core (runtime)
  ↕  InteractionManager / InteractionRouter
  ↕  Visibility dict (runtime_state, steps, prompts, answers)
  ↕
EngineFacade (desktop boundary — keep as-is)
  ↕  submit_text() / snapshot()
  ↕
Presenters (adapt visibility → view models — keep, extend for panel fields)
  ↕
PanelController (replace ConversationController)
  ↕
PanelWidget (replace ShellWidgets layout — new vertical panel)
  ├── StateRowWidget
  ├── CurrentActionWidget
  ├── ConfirmationZoneWidget  (conditional)
  ├── LastExchangeStrip
  └── InputBarWidget
```

**Future ARIA client** (if JARVIS moves to a separate runtime/API model):
- `EngineFacade` becomes an HTTP/WebSocket client stub — same interface, different backend
- `PanelController` does not need to change
- View models remain identical
- The panel UI is transport-agnostic by design

**Key principle**: the panel must never have knowledge of what action JARVIS ran. It only
knows runtime state and the visibility dict. This keeps the panel reusable across future
backends (ARIA, local, remote).

---

# Files Likely To Change

| File | Change Type | Reason |
|------|-------------|--------|
| `desktop/shell/layout.py` | Replace | Horizontal split → single vertical column |
| `desktop/shell/main_window.py` | Significant edit | Window size, frameless mode, panel geometry |
| `desktop/shell/theme.py` | Replace entirely | Dark system theme |
| `desktop/shell/widgets/conversation_view.py` | Reduce | Becomes `LastExchangeStrip` — compact, not primary |
| `desktop/shell/widgets/composer.py` | Replace | Multi-line composer → `InputBarWidget` (single-line) |
| `desktop/shell/widgets/status_panel.py` | Replace | Form-field status → `StateRowWidget` + `CurrentActionWidget` |
| `desktop/shell/controllers/conversation_controller.py` | Replace | `PanelController` — same wiring pattern, different widget targets |
| `desktop/backend/view_models.py` | Extend | Add `last_exchange` field to `SessionSnapshotViewModel` |
| `desktop/backend/presenters.py` | Extend | Populate new view model fields for panel sections |

| File | Change Type | Reason |
|------|-------------|--------|
| `desktop/backend/engine_facade.py` | No change | Interface is correct as-is |
| `desktop/backend/session_service.py` | Minor | Expose `last_n_entries(n)` for the strip |
| `desktop/app/application.py` | Minor | Remove Fusion style, apply dark theme |
| `desktop/main.py` | No change | Entry point is fine |

---

# Out Of Scope

The following are explicitly out of scope for this direction change:

- Redesigning the JARVIS core runtime or InteractionManager
- Adding new command types or expanding what JARVIS can do
- Building a full settings / preferences UI
- Adding conversation search, history browser, or session management
- Multi-window or detachable panel modes
- Mobile or web clients
- Implementing voice wake word detection
- Adding a system tray icon or menubar integration (can follow later)
- Dark mode toggle or theme switching (dark is the only theme)
- Accessibility / WCAG compliance audit (follow-on task)
- Notification system outside the panel
- Any AI model or backend changes

---

# Acceptance Criteria

The desktop direction is correct when all of the following are true:

1. The panel fits in **420px wide or less** without horizontal scrolling or truncation.
2. A user can read **current mode + current runtime state** in under 2 seconds without scrolling.
3. A **pending confirmation prompt** is immediately visible without the user searching for it.
4. The **last user input and last JARVIS response** are visible without opening any overlay.
5. The **input bar** is always reachable without scrolling.
6. The panel **does not block the primary work area** when positioned at screen edge.
7. The visual theme reads as **dark, compact, system-like** — not as a chat app or consumer tool.
8. All **confirmation and cancellation** actions are reachable without leaving the panel.
9. There is **no full chat transcript** visible by default.
10. The `EngineFacade` interface is **unchanged** — the panel change is purely a presentation layer change.
