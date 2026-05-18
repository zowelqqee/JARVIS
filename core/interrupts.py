from __future__ import annotations

import re
import threading


_INTERRUPT_EVENT = threading.Event()
_STOP_WORD_RE = re.compile(
    r"^\s*(?:"
    r"jarvis|джарвис|hey\s+jarvis|okay\s+jarvis|окей\s+джарвис|"
    r"friday|f\.?\s*r\.?\s*i\.?\s*d\.?\s*a\.?\s*y\.?|"
    r"hey\s+friday|okay\s+friday|фрайдей|эй\s+фрайдей|окей\s+фрайдей"
    r")?"
    r"[\s,.:;!\-]*(?:стоп|stop|отмена|cancel|хватит|прекрати)\s*[.!?]*\s*$",
    re.IGNORECASE,
)


def is_stop_phrase(text: str) -> bool:
    return bool(_STOP_WORD_RE.match(text or ""))


def request_interrupt(reason: str = "stop") -> None:
    _INTERRUPT_EVENT.set()
    print(f"[Interrupt] Requested: {reason}")


def clear_interrupt() -> None:
    _INTERRUPT_EVENT.clear()


def is_interrupted() -> bool:
    return _INTERRUPT_EVENT.is_set()
