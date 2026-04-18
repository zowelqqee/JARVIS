"""
Formats arbitrary text into at most 4 lines of 20 characters each for OLED display.
Words are never split mid-word.
"""

LINE_WIDTH = 20
MAX_LINES  = 4


def format_for_oled(text: str) -> list[str]:
    """
    Split *text* into at most MAX_LINES lines of at most LINE_WIDTH chars.
    Words are not broken — long single words get their own line truncated at LINE_WIDTH.
    Returns a list of 1–4 strings.
    """
    words  = text.split()
    lines: list[str] = []
    current = ""

    for word in words:
        if len(lines) >= MAX_LINES:
            break

        # Truncate a single word that exceeds LINE_WIDTH
        if len(word) > LINE_WIDTH:
            word = word[:LINE_WIDTH]

        if not current:
            current = word
        elif len(current) + 1 + len(word) <= LINE_WIDTH:
            current = current + " " + word
        else:
            lines.append(current)
            if len(lines) >= MAX_LINES:
                break
            current = word

    if current and len(lines) < MAX_LINES:
        lines.append(current)

    return lines or [""]
