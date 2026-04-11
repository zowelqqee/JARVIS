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

    QListWidget#conversationList {
        background: transparent;
        border: none;
        outline: none;
        padding: 2px;
    }

    QListWidget#conversationList::item {
        background-color: #fbf6ee;
        border: 1px solid #dfd2c0;
        border-radius: 14px;
        color: #22303a;
        padding: 12px 14px;
        margin: 0 0 10px 0;
    }

    QListWidget#conversationList::item:selected {
        background-color: #e7f2ef;
        border: 1px solid #90c3bc;
        color: #123136;
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

    QPushButton#composerSendButton {
        min-width: 108px;
        padding: 10px 18px;
        border: none;
        border-radius: 14px;
        background-color: #0f766e;
        color: #fffdf8;
        font-weight: 700;
    }

    QPushButton#composerSendButton:hover {
        background-color: #0b635d;
    }

    QPushButton#composerSendButton:pressed {
        background-color: #0a5450;
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

    QLabel {
        color: #1f2933;
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
