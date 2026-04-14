# Desktop Shell Progress

---

## Pass 1 — Panel Layout Contract Implementation

**Status:** Complete  
**Date:** 2026-04-14  
**Source of truth:** `docs/current/jarvis_desktop_panel_direction.md`

---

### Summary

Replaced the old Tkinter `JarvisUI` layout with a panel-first PySide6 desktop
under `desktop/`. The new shell enforces the exact 6-section layout contract
from the direction document, all state-driven content rules for 8 runtime
states, and the width contract. The Gemini Live backend (`main.py`) is
unchanged in behaviour — only 4 minimal `hasattr`-guarded callback insertions
were added.

---

### What Was Built

#### `desktop/` package (new)

| File | Role |
|------|------|
| `desktop/main.py` | New entry point — runs panel + JarvisLive in background thread |
| `desktop/app/application.py` | QApplication setup, dark palette, monospace font |
| `desktop/backend/view_models.py` | `PanelState`, `PendingPrompt` data contracts |
| `desktop/backend/panel_bridge.py` | Thread-safe bridge: JarvisLive → panel state via QTimer-drained queue |
| `desktop/shell/theme.py` | Dark palette constants + full Qt stylesheet |
| `desktop/shell/main_window.py` | Frameless QMainWindow, 400×520 default, 360–440px width |
| `desktop/shell/panel_widget.py` | Container: assembles 6 sections, manages PromptZone lifecycle |
| `desktop/shell/panel_controller.py` | Wires `bridge.state_updated` ↔ `panel.update_state` |
| `desktop/shell/widgets/titlebar.py` | Section 1 — 32px, `[●] JARVIS [–][×]`, drag region |
| `desktop/shell/widgets/state_row.py` | Section 2 — 28px, mode chip + runtime state chip |
| `desktop/shell/widgets/current_action.py` | Section 3 — min 48px, max 3 lines, state-driven text |
| `desktop/shell/widgets/prompt_zone.py` | Section 4 — conditional, confirmation + clarification kinds |
| `desktop/shell/widgets/last_exchange.py` | Section 5 — 2-row strip, truncated last exchange |
| `desktop/shell/widgets/input_bar.py` | Section 6 — single-line input, state-dependent placeholder/disabled |

#### `main.py` (root) — minimal changes

4 `hasattr`-guarded callbacks inserted:
- `set_connecting()` — at start of `run()` while-loop before connect
- `set_executing(name, args)` — before tool execution in `_execute_tool`
- `set_idle()` — after tool execution in `_execute_tool`
- `set_failed(msg)` — in `run()` exception handler

All calls are no-ops when `ui` is the original `JarvisUI` (backward compatible).

---

### Layout Contract Verification (tested with offscreen Qt)

| Constraint | Status |
|-----------|--------|
| Fixed 6-section order | ✅ 6 layout items confirmed |
| Sections 1,2,3,5,6 always visible | ✅ Never hidden |
| Section 4 (PromptZone) conditional | ✅ Layout goes 6→7→6 on insert/remove |
| PromptZone removed from widget tree (not hidden) | ✅ `removeWidget` + `deleteLater` |
| Width: min 360, preferred 400, max 440 | ✅ Enforced on QMainWindow |
| Height: 520 default, min 420 | ✅ |
| All 8 runtime states mapped | ✅ |
| Input bar disabled for 5 states | ✅ thinking, executing, answering, awaiting_* |
| State-dependent placeholder text | ✅ All 8 states covered |

---

### How To Run

```bash
# Panel-first desktop (PySide6)
.venv-desktop-packaging/bin/python -m desktop.main

# Or directly
.venv-desktop-packaging/bin/python desktop/main.py
```

The panel starts in **demo mode** if the backend (`main.py`) cannot be imported
(e.g., if Windows-only packages like `comtypes`/`pycaw` are not installed on macOS).
The panel UI is fully functional in demo mode for structural testing.

---

### What Remains For Pass 2 (Visual / Style)

| Item | Notes |
|------|-------|
| Chip opacity pulse animation | Slow 0.6→1.0→0.6 cycle on EXECUTING/PARSING chip |
| Window drop shadow | `0 8px 32px rgba(0,0,0,0.6)` on macOS — needs compositing |
| Window always-on-top toggle | Optional preference |
| Font warning: SF Mono missing | On systems without SF Mono, falls back to Menlo. No functional issue. |
| Full log overlay | Clicking LastExchangeStrip opens scrollable full history |
| System tray / menubar integration | Out of scope for pass 1+2 |
| Pixel-perfect spacing | 12px section dividers, 8px chip gap — fine-tuning |
| Mic toggle wired to actual mute | Currently visual indicator only (Gemini Live is always-on mic) |
| macOS-native frameless shadow | `setAttribute(WA_TranslucentBackground)` + custom painting |
| Resize handle | Vertical resize only, dragging bottom edge |
