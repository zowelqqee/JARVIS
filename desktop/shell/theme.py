"""
Dark panel theme — first pass.

Colours and structure per jarvis_desktop_panel_direction.md.
Visual polish (animations, shadows, exact pixel-perfect spacing) is deferred
to the second pass.
"""

# ── Palette ──────────────────────────────────────────────────────────────── #

BG          = "#0d0d0f"    # near-black window background
SURFACE     = "#111215"    # panel card surface
BORDER      = "#1e2028"    # hairline border
TEXT_PRI    = "#e8eaed"    # primary text
TEXT_SEC    = "#6b7280"    # secondary / dimmed text
ACCENT      = "#3b82f6"    # system blue — active state, chip

# Chip colours by state
CHIP_IDLE       = "#374151"
CHIP_ACTIVE     = ACCENT       # listening / thinking / executing / answering
CHIP_WAITING    = "#f59e0b"    # awaiting_clarification / awaiting_confirmation
CHIP_ERROR      = "#ef4444"    # failed

# Dot indicator colours (titlebar)
DOT_IDLE        = CHIP_IDLE
DOT_ACTIVE      = ACCENT
DOT_WAITING     = CHIP_WAITING
DOT_ERROR       = CHIP_ERROR


def state_chip_color(runtime_state: str) -> str:
    """Return background colour for the runtime state chip."""
    if runtime_state in ("listening", "thinking", "executing", "answering"):
        return CHIP_ACTIVE
    if runtime_state in ("awaiting_clarification", "awaiting_confirmation"):
        return CHIP_WAITING
    if runtime_state == "failed":
        return CHIP_ERROR
    return CHIP_IDLE


def dot_color(runtime_state: str) -> str:
    """Return colour for the titlebar ● dot."""
    if runtime_state in ("listening", "thinking", "executing", "answering"):
        return DOT_ACTIVE
    if runtime_state in ("awaiting_clarification", "awaiting_confirmation"):
        return DOT_WAITING
    if runtime_state == "failed":
        return DOT_ERROR
    return DOT_IDLE


# ── Stylesheet ───────────────────────────────────────────────────────────── #

DARK_STYLESHEET = f"""
/* ── Window ──────────────────────────────────────────── */
QMainWindow {{
    background-color: {BG};
}}

QWidget {{
    background-color: {BG};
    color: {TEXT_PRI};
    font-family: "SF Mono", "JetBrains Mono", "Menlo", "Consolas", "Courier New";
    font-size: 11px;
}}

/* ── Scrollbars (minimal) ────────────────────────────── */
QScrollBar:vertical {{
    background: {BG};
    width: 4px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 2px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

/* ── Labels ──────────────────────────────────────────── */
QLabel {{
    background: transparent;
    color: {TEXT_PRI};
}}

/* ── Line Edit (input bar) ───────────────────────────── */
QLineEdit {{
    background-color: {SURFACE};
    color: {TEXT_PRI};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus {{
    border: 1px solid {ACCENT};
}}
QLineEdit:disabled {{
    color: {TEXT_SEC};
    background-color: {BG};
}}
QLineEdit::placeholder {{
    color: {TEXT_SEC};
}}

/* ── Buttons ─────────────────────────────────────────── */
QPushButton {{
    background-color: {SURFACE};
    color: {TEXT_PRI};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 12px;
}}
QPushButton:hover {{
    border-color: {ACCENT};
}}
QPushButton:pressed {{
    background-color: {BORDER};
}}
QPushButton:disabled {{
    color: {TEXT_SEC};
    border-color: {BG};
}}

QPushButton#confirmBtn {{
    background-color: {ACCENT};
    color: #ffffff;
    border: none;
}}
QPushButton#confirmBtn:hover {{
    background-color: #2563eb;
}}
QPushButton#confirmBtn:pressed {{
    background-color: #1d4ed8;
}}

QPushButton#sendBtn {{
    background-color: {ACCENT};
    color: #ffffff;
    border: none;
    padding: 5px 10px;
}}
QPushButton#sendBtn:hover {{
    background-color: #2563eb;
}}
QPushButton#sendBtn:disabled {{
    background-color: {BORDER};
    color: {TEXT_SEC};
}}

QPushButton#micBtn {{
    background-color: transparent;
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 6px;
    color: {TEXT_SEC};
    font-size: 14px;
}}
QPushButton#micBtn:hover {{
    border-color: {ACCENT};
    color: {TEXT_PRI};
}}

QPushButton#minBtn, QPushButton#closeBtn {{
    background-color: transparent;
    border: none;
    color: {TEXT_SEC};
    padding: 2px 6px;
    font-size: 13px;
    border-radius: 4px;
}}
QPushButton#minBtn:hover, QPushButton#closeBtn:hover {{
    color: {TEXT_PRI};
    background-color: {BORDER};
}}
QPushButton#closeBtn:hover {{
    color: {CHIP_ERROR};
}}
"""
