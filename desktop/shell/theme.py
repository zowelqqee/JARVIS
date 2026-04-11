"""Visual theme for the JARVIS desktop application."""

from __future__ import annotations


def apply_app_theme(app: object) -> None:
    """Apply the shared desktop theme to the active QApplication."""
    from PySide6.QtGui import QColor, QFont, QPalette

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#f3ede2"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#1f2933"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#fffdf8"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#f7f2e9"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#fffdf8"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#1f2933"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#1f2933"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#fcf7ef"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#1f2933"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#fffdf8"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#0f766e"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#fffdf8"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#8c8579"))

    font = QFont("Segoe UI", 10)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)

    app.setStyle("Fusion")
    app.setPalette(palette)
    app.setFont(font)
    app.setStyleSheet(build_stylesheet())


def build_stylesheet() -> str:
    """Return the shared Qt stylesheet for the desktop app."""
    return """
    QMainWindow#mainWindow {
        background-color: #f3ede2;
    }

    QWidget#shellRoot {
        background-color: qlineargradient(
            x1: 0,
            y1: 0,
            x2: 1,
            y2: 1,
            stop: 0 #f8f2e7,
            stop: 0.55 #f2eadf,
            stop: 1 #ede3d5
        );
    }

    QWidget#conversationCard,
    QWidget#composerCard,
    QWidget#statusCard {
        background-color: #fffdf8;
        border: 1px solid #dccfbc;
        border-radius: 20px;
    }

    QWidget#composerCard,
    QWidget#statusCard {
        padding: 6px;
    }

    QLabel#conversationTitle,
    QLabel#composerTitle,
    QLabel#statusPanelTitle {
        color: #1f2933;
        font-size: 21px;
        font-weight: 700;
        letter-spacing: 0.2px;
    }

    QLabel#conversationSubtitle,
    QLabel#composerSubtitle,
    QLabel#statusPanelSubtitle,
    QLabel#conversationEmptyState {
        color: #6d665b;
        font-size: 12px;
        line-height: 1.35;
    }

    QLabel#conversationEmptyState {
        border: 1px dashed #d7cab8;
        border-radius: 16px;
        padding: 24px 18px;
        background-color: #fcf7ef;
    }

    QWidget#composerVoicePanel,
    QWidget#composerTextPanel {
        background-color: #fcf7ef;
        border: 1px solid #dfd2c0;
        border-radius: 16px;
    }

    QLabel#composerSectionLabel {
        color: #1f2933;
        font-size: 13px;
        font-weight: 700;
    }

    QLabel#composerTextHint,
    QLabel#composerSupportText,
    QLabel#composerVoiceDetail,
    QLabel#composerDivider {
        color: #6d665b;
        font-size: 12px;
        line-height: 1.35;
    }

    QLabel#composerDivider {
        color: #8b816f;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1.4px;
        padding: 0 2px;
    }

    QLabel#composerVoiceStatePill {
        background-color: #dff0ec;
        border: 1px solid #9ecac2;
        border-radius: 10px;
        color: #0f5f5a;
        font-size: 11px;
        font-weight: 700;
        padding: 3px 8px;
    }

    QLabel#composerVoiceStatePill[voiceState="listening"] {
        background-color: #eef6f4;
        border-color: #0f766e;
        color: #0b635d;
    }

    QLabel#composerVoiceStatePill[voiceState="routing"] {
        background-color: #f7f1e7;
        border-color: #dbc9a6;
        color: #7a6130;
    }

    QLabel#composerVoiceStatePill[voiceState="error"],
    QLabel#composerVoiceStatePill[voiceState="unavailable"] {
        background-color: #fff1ee;
        border-color: #e0b0a7;
        color: #8a4a3c;
    }

    QListWidget#conversationList {
        background: transparent;
        border: none;
        outline: none;
        padding: 2px;
    }

    QListWidget#conversationList::item {
        background: transparent;
        border: none;
        color: #22303a;
        padding: 0;
        margin: 0 0 10px 0;
    }

    QListWidget#conversationList::item:selected {
        background: transparent;
        border: none;
        color: #123136;
    }

    QFrame#transcriptEntryCard {
        background-color: #fbf6ee;
        border: 1px solid #dfd2c0;
        border-radius: 14px;
    }

    QFrame#transcriptEntryCard[entryRole="user"] {
        background-color: #eef5f3;
        border-color: #b7d8d1;
    }

    QFrame#transcriptEntryCard[surfaceKind="question_answer"],
    QFrame#transcriptEntryCard[surfaceKind="command_completion"] {
        border-color: #c6d9cf;
    }

    QFrame#transcriptEntryCard[surfaceKind="clarification_prompt"],
    QFrame#transcriptEntryCard[surfaceKind="confirmation_prompt"],
    QFrame#transcriptEntryCard[surfaceKind="command_blocked"] {
        background-color: #fff8ec;
        border-color: #e4cf9f;
    }

    QFrame#transcriptEntryCard[surfaceKind="command_failure"],
    QFrame#transcriptEntryCard[surfaceKind="question_failure"] {
        background-color: #fff1ee;
        border-color: #e0b0a7;
    }

    QFrame#transcriptEntryCard[surfaceKind="system_warning"] {
        background-color: #fff7e3;
        border-color: #dfc37c;
    }

    QLabel#transcriptRolePill,
    QLabel#transcriptSurfacePill,
    QLabel#transcriptStatePill,
    QLabel#transcriptReplyChip,
    QPushButton#transcriptReplyChipButton {
        background-color: #f0e7da;
        border: 1px solid #d8cab6;
        border-radius: 10px;
        color: #5e574d;
        font-size: 11px;
        font-weight: 700;
        padding: 3px 8px;
    }

    QLabel#transcriptSurfacePill {
        background-color: #dff0ec;
        border-color: #9ecac2;
        color: #0f5f5a;
    }

    QLabel#transcriptStatePill {
        background-color: #f7f1e7;
        border-color: #dbc9a6;
        color: #7a6130;
    }

    QLabel#transcriptReplyChip {
        background-color: #f3ece2;
        color: #574d40;
    }

    QPushButton#transcriptReplyChipButton:hover {
        border-color: #0f766e;
        color: #0f5f5a;
        background-color: #edf6f4;
    }

    QPushButton#transcriptReplyChipButton:pressed {
        background-color: #dff0ec;
    }

    QLabel#transcriptSummaryText {
        color: #0f5f5a;
        font-size: 12px;
        font-weight: 700;
    }

    QLabel#transcriptPrimaryText {
        color: #22303a;
        font-size: 13px;
        line-height: 1.45;
    }

    QLabel#transcriptSectionHeading {
        color: #1f2933;
        font-size: 12px;
        font-weight: 700;
        margin-top: 4px;
    }

    QLabel#transcriptSecondaryText,
    QLabel#transcriptListMeta {
        color: #5e574d;
        font-size: 12px;
        line-height: 1.35;
    }

    QLabel#transcriptListMeta {
        color: #7b7367;
    }

    QFrame#transcriptResultItem {
        background-color: #fffdfa;
        border: 1px solid #e1d7c9;
        border-radius: 10px;
    }

    QLabel#transcriptResultItemTitle {
        color: #24323b;
        font-size: 12px;
        font-weight: 700;
    }

    QLabel#transcriptResultItemDetail {
        color: #7b7367;
        font-size: 11px;
    }

    QPlainTextEdit#composerInput {
        background-color: #fffdfa;
        border: 1px solid #d8cab6;
        border-radius: 16px;
        color: #1f2933;
        padding: 14px 16px;
        selection-background-color: #0f766e;
        selection-color: #fffdf8;
    }

    QPlainTextEdit#composerInput:focus {
        border: 2px solid #0f766e;
        padding: 13px 15px;
        background-color: #ffffff;
    }

    QPlainTextEdit#composerInput[readOnly="true"] {
        background-color: #f4eee5;
        color: #756f66;
    }

    QPushButton#composerVoiceButton {
        min-height: 52px;
        padding: 12px 18px;
        border: none;
        border-radius: 14px;
        background-color: #0f766e;
        color: #fffdf8;
        font-size: 14px;
        font-weight: 700;
    }

    QPushButton#composerVoiceButton:hover:enabled {
        background-color: #0b635d;
    }

    QPushButton#composerVoiceButton:pressed:enabled {
        background-color: #0a5450;
    }

    QPushButton#composerVoiceButton:disabled {
        background-color: #cfc8bd;
        color: #8f877a;
    }

    QPushButton#composerSendButton {
        min-width: 108px;
        padding: 10px 18px;
        border: 1px solid #d4c5b2;
        border-radius: 14px;
        background-color: #f7f1e7;
        color: #1f2933;
        font-weight: 700;
    }

    QPushButton#composerSendButton:hover {
        border-color: #0f766e;
        color: #0f5f5a;
        background-color: #eef6f4;
    }

    QPushButton#composerSendButton:pressed {
        background-color: #dff0ec;
    }

    QPushButton#composerSendButton:disabled {
        background-color: #cfc8bd;
        color: #8f877a;
    }

    QPushButton#speechToggleButton {
        min-height: 42px;
        padding: 10px 14px;
        border-radius: 14px;
        border: 1px solid #d4c5b2;
        background-color: #f7f1e7;
        color: #1f2933;
        font-weight: 600;
    }

    QPushButton#speechToggleButton:hover {
        border-color: #0f766e;
        color: #0f5f5a;
    }

    QPushButton#speechToggleButton:checked {
        background-color: #d7ece8;
        border-color: #0f766e;
        color: #0d4f4a;
    }

    QPushButton#statusActionButton {
        min-height: 38px;
        padding: 8px 12px;
        border-radius: 12px;
        border: 1px solid #d4c5b2;
        background-color: #f7f1e7;
        color: #1f2933;
        font-weight: 600;
    }

    QPushButton#statusActionButton:hover:enabled {
        border-color: #0f766e;
        color: #0f5f5a;
        background-color: #eef6f4;
    }

    QPushButton#statusActionButton:pressed:enabled {
        background-color: #dff0ec;
    }

    QPushButton#statusActionButton:disabled {
        background-color: #f4eee5;
        color: #9a9184;
        border-color: #ddd2c3;
    }

    QLabel {
        color: #1f2933;
    }

    QLabel#statusPanelValue {
        color: #2e3a42;
    }

    QStatusBar#appStatusBar {
        background-color: #fcf7ef;
        border-top: 1px solid #d8cab6;
        color: #5e574d;
    }

    QStatusBar#appStatusBar::item {
        border: none;
    }

    QScrollBar:vertical {
        background: transparent;
        width: 12px;
        margin: 4px 0 4px 0;
    }

    QScrollBar::handle:vertical {
        background: #cdbda8;
        min-height: 36px;
        border-radius: 6px;
    }

    QScrollBar::handle:vertical:hover {
        background: #b9a68d;
    }

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical,
    QScrollBar::sub-page:vertical {
        background: none;
        border: none;
        height: 0px;
    }
    """
