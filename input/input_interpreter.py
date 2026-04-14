"""LLM-assisted input normalization layer for JARVIS voice-first shell.

Sits between voice normalization and the deterministic router.
Optional, stateless, fail-safe: every error path returns the original text unchanged.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Named constants — auditable in one place
# ---------------------------------------------------------------------------

_INTERPRETER_CONFIDENCE_THRESHOLD = 0.70
_INTERPRETER_MAX_LENGTH_MULTIPLIER = 3
_INTERPRETER_TIMEOUT_SECONDS = 5.0
_INTERPRETER_MODEL = "claude-haiku-4-5-20251001"

# ---------------------------------------------------------------------------
# Fix 2: Polite command forms targeting supported v1 intents
# Only verbs that are NOT already covered by the router's _POLITE_COMMAND_PREFIXES.
# "can you open/launch/start/close/find/search" are already in the router; excluded here.
# ---------------------------------------------------------------------------

_POLITE_COMMAND_SUBJECTS = ("can you ", "could you ", "would you ")
_POLITE_V1_COMMAND_VERBS = (
    "resume",         # run_protocol: resume_work — not in router's polite prefix list
    "start work",     # prepare_workspace — exact canonical form
    "start working",  # prepare_workspace — conjugated voice form
)

# ---------------------------------------------------------------------------
# Fix 3: "resume ... on <workspace>" deterministic v1 normalization rule.
# Maps to "start work on <workspace>" (prepare_workspace intent).
# Pattern is intentionally narrow: requires "resume" + "on" + at least one non-space char.
# ---------------------------------------------------------------------------

_RESUME_ON_PATTERN = re.compile(r'\bresume\b.*?\bon\s+(\S.*)', re.IGNORECASE)

# ---------------------------------------------------------------------------
# Fix 4: Hero-flow voice near-miss rescue (v1 only, deterministic, no LLM).
# Catches obvious STT near-miss variants of "start work" / "resume work" before
# they fall through to generic clarification or question-failure paths.
# Narrowly scoped to these two hero-flow phrases only.
#
# Tier 1 — first-word typo, second word is exact "work":
#   e.g. "stat work", "tart work on JARVIS"  → high confidence, normalize silently.
# Tier 2 — first word is exact, second-word "work" typo:
#   e.g. "start wrk", "resume wark on JARVIS" → normalize silently with a
#   clarification hint surfaced in the debug trace.
# ---------------------------------------------------------------------------

_HERO_NEAR_MISS_START_T1 = re.compile(
    r'^(?:stat|tart|stort|sart|strat|startt|strt)\s+work(?:\s+(?:on|in)\s+(.+))?$',
    re.IGNORECASE,
)
_HERO_NEAR_MISS_RESUME_T1 = re.compile(
    r'^(?:rezume|resome|resum|resumw|rezoom)\s+work(?:\s+(?:on|in)\s+(.+))?$',
    re.IGNORECASE,
)
_HERO_NEAR_MISS_START_T2 = re.compile(
    r'^start\s+(?:wrk|wark|wrok|woork|wok)(?:\s+(?:on|in)\s+(.+))?$',
    re.IGNORECASE,
)
_HERO_NEAR_MISS_RESUME_T2 = re.compile(
    r'^resume\s+(?:wrk|wark|wrok|woork|wok)(?:\s+(?:on|in)\s+(.+))?$',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Known app aliases — used for entity grounding check
# ---------------------------------------------------------------------------

_APP_ALIASES: dict[str, str] = {
    "notes app": "Notes",
    "notes": "Notes",
    "vs code": "Visual Studio Code",
    "vscode": "Visual Studio Code",
    "visual studio code": "Visual Studio Code",
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "safari": "Safari",
    "terminal": "Terminal",
    "finder": "Finder",
    "telegram": "Telegram",
    "slack": "Slack",
    "spotify": "Spotify",
    "messages": "Messages",
    "mail": "Mail",
    "calendar": "Calendar",
    "xcode": "Xcode",
}

# ---------------------------------------------------------------------------
# System prompt — narrow, task-specific, includes non-execution constraint
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are the input normalization layer for JARVIS, a voice-first desktop assistant.

Your ONLY job is to normalize natural, spoken, typed, or mixed-language input into
canonical command text for a fixed set of supported intents. You are the primary
input understanding layer, not a fallback.

## Supported intents (v1 only)

| Intent | Canonical English form |
|--------|------------------------|
| run_protocol: resume_work | "resume work" |
| prepare_workspace | "start work" or "start work on <workspace>" |
| open_app | "open <app>" — where <app> is a recognized app name |
| open_folder | "open the <name> folder" |
| close_app | "close <app>" |
| search_local | "search <folder> for <query>" or "find files named <query> in <folder>" |

## Russian-language normalization

Russian or mixed-language input MUST be normalized to the English canonical form above.

Examples (Russian → canonical English):
- "начни работу" → "start work"
- "начать работу" → "start work"
- "подготовь рабочее пространство" → "start work"
- "продолжи работу" → "resume work"
- "возобновить работу" → "resume work"
- "вернись к работе" → "resume work"
- "открой телеграм" → "open Telegram"
- "закрой телеграм" → "close Telegram"

Mixed-script examples:
- "Старт work" → "start work"
- "Старт work on JARVIS" → "start work on JARVIS"

## Hard rules

1. Normalize ONLY toward the supported intents above. Never invent new intents.
2. Never invent entities not present or strongly implied in the raw input text.
3. Never resolve ambiguous entities — leave entity_hints empty if uncertain.
4. Questions stay questions: routing_hint must be "question" for any question form.
5. If unsure, return routing_hint = "unclear" and normalized_text equal to the original.
6. Compound or multi-step inputs: return routing_hint = "unclear".
7. open_website, confirm, cancel, or any other unsupported intent: routing_hint = "unclear".
8. Do NOT produce any action, command, or executable output. Return ONLY a JSON normalization object.
9. If the input is already in canonical English form, return it unchanged with confidence 1.0.

## Output schema (valid JSON only, no prose, no markdown)

{
  "normalized_text": "<canonical form, or original input unchanged if no rewrite needed>",
  "routing_hint": "command" | "question" | "unclear",
  "intent_hint": "<intent string, or null>",
  "entity_hints": {"<role>": "<entity from input>"},
  "confidence": <float 0.0-1.0>,
  "debug_note": "<short explanation, 1 sentence>"
}\
"""

# ---------------------------------------------------------------------------
# Fast-path gate constants — LLM-first architecture
#
# The goal is to keep the fast-path narrow.  Only inputs where the LLM adds
# NO value are bypassed.  Everything else goes through the LLM first.
#
# Not on fast-path (LLM primary path):
#   - "open Telegram", "start work", "prepare workspace" — LLM confirms/normalizes
#   - "can you resume work", "let's get to work"        — LLM normalizes
#   - "начни работу", "Старт work"                      — LLM normalizes to English
# ---------------------------------------------------------------------------

# Short terminal replies — always unambiguous; LLM adds nothing.
_EXACT_REPLY_WORDS: frozenset[str] = frozenset({
    "yes", "no", "confirm", "cancel", "answer", "execute", "y", "n",
})

# Question starters used by _is_obvious_fast_path — EXCLUDES "can/could/would/should"
# because those also introduce polite command forms ("can you resume work").
# Full set retained in _QUESTION_STARTERS below for the safety boundary check.
_FAST_PATH_QUESTION_STARTERS = (
    "what ",
    "how ",
    "why ",
    "which ",
    "where ",
    "when ",
    "who ",
    "compare ",
    "explain ",
    "is ",
    "are ",
    "does ",
    "do ",
    "did ",
)

# Full question starter set — used ONLY for _is_question_input (safety boundary 1).
# Includes "can/could/would/should" so the safety boundary fires correctly when the
# LLM returns routing_hint="command" for a genuine question.
# _is_polite_v1_command carves out the polite-command exception.
_QUESTION_STARTERS = (
    "what ",
    "how ",
    "why ",
    "which ",
    "where ",
    "when ",
    "who ",
    "compare ",
    "explain ",
    "is ",
    "are ",
    "does ",
    "do ",
    "did ",
    "can ",
    "could ",
    "would ",
    "should ",
)

# ---------------------------------------------------------------------------
# Kept from heuristic era — intentionally left in place for this migration step.
# _NATURAL_SPEECH_MARKERS and _CANONICAL_COMMAND_STARTERS have been removed;
# the LLM now handles the distinction between natural and canonical forms.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class InterpretedInput:
    normalized_text: str
    routing_hint: str | None
    intent_hint: str | None
    entity_hints: dict[str, str]
    confidence: float
    debug_note: str | None
    skipped: bool
    raw_input_seen: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _interpreter_disabled() -> bool:
    return os.environ.get("JARVIS_INTERPRETER_DISABLED", "").strip() == "1"


def _is_polite_v1_command(text: str) -> bool:
    """Return True when text is a polite command form targeting a supported v1 intent.

    Used ONLY by _is_question_input (safety boundary 1).  Not used by the fast-path
    gate — in the LLM-first architecture polite command forms reach the LLM directly.

    Narrowly scoped: only subject-verb combinations where the router's own
    _POLITE_COMMAND_PREFIXES list has no matching entry.  Prevents the safety boundary
    from incorrectly blocking "can you resume work" → "command" as a question-command
    conflict when the LLM correctly classifies it as a command.
    """
    for subject in _POLITE_COMMAND_SUBJECTS:
        if text.startswith(subject):
            remainder = text[len(subject):]
            if any(remainder.startswith(verb) for verb in _POLITE_V1_COMMAND_VERBS):
                return True
    return False


def _is_obvious_fast_path(text: str) -> bool:
    """Return True when the LLM adds no value and the input should bypass it.

    Deliberately narrow — only skip the LLM when the input is unambiguously handled
    by the downstream pipeline without normalization.  Everything else goes through
    the LLM first (LLM-first architecture, step 1).

    Fast-path cases:
    - Empty input
    - Short unambiguous terminal replies (yes/no/confirm/cancel/answer/execute)
    - Clear questions starting with unambiguous question words (not can/could/would/should,
      which also introduce polite command forms)
    - Input that ends with "?"

    NOT on fast-path (goes to LLM):
    - All command-like inputs, even exact canonical ones like "start work" or "open Telegram"
      (LLM confirms them unchanged at confidence 1.0 — adds one round-trip, preserves
      the architecture invariant)
    - Polite command forms ("can you resume work", "could you start working")
    - Russian or mixed-language inputs
    - Any input containing natural speech
    """
    lowered = text.lower().strip()
    if not lowered:
        return True

    # Short unambiguous terminal replies — LLM adds nothing
    if lowered in _EXACT_REPLY_WORDS:
        return True

    # Clear questions starting with unambiguous question words
    # "can/could/would/should" are excluded because "can you resume work" is a command.
    if any(lowered.startswith(qs) for qs in _FAST_PATH_QUESTION_STARTERS) or lowered.endswith("?"):
        return True

    return False


def _ground_entities(entity_hints: dict[str, str], raw_input: str) -> dict[str, str]:
    """Strip entity hints whose values are not grounded in the raw input.

    An entity is grounded when:
    - Its value appears as a case-insensitive substring of the raw input, OR
    - A known alias of the value appears in the raw input.
    """
    if not entity_hints:
        return {}

    lowered_input = raw_input.lower()
    grounded: dict[str, str] = {}

    for role, entity in entity_hints.items():
        entity_lower = entity.lower().strip()
        if not entity_lower:
            continue

        # Direct substring match
        if entity_lower in lowered_input:
            grounded[role] = entity
            continue

        # Alias match: check if any alias of the entity appears in the input
        for alias, canonical in _APP_ALIASES.items():
            if canonical.lower() == entity_lower and alias in lowered_input:
                grounded[role] = entity
                break

    return grounded


def _is_question_input(text: str) -> bool:
    """Mirror the router's question detection for the safety boundary check.

    Polite command forms for supported v1 intents are never treated as questions
    even when they start with "can/could/would" (Fix 2).
    """
    lowered = text.lower().strip()
    if _is_polite_v1_command(lowered):
        return False
    return (
        lowered.endswith("?")
        or any(lowered.startswith(qs) for qs in _QUESTION_STARTERS)
    )


def _call_llm(text: str) -> tuple[dict, float]:
    """Call the Anthropic API and return (parsed_json, latency_ms).

    Raises on timeout, API error, or import failure.
    All exceptions are caught by the caller.
    """
    try:
        import anthropic  # noqa: PLC0415 — conditional import, SDK may not be present
    except ImportError as exc:
        raise RuntimeError("anthropic SDK not available") from exc

    client = anthropic.Anthropic(timeout=_INTERPRETER_TIMEOUT_SECONDS)
    t0 = time.monotonic()

    response = client.messages.create(
        model=_INTERPRETER_MODEL,
        max_tokens=256,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Normalize this input:\n{text}",
            }
        ],
    )

    latency_ms = (time.monotonic() - t0) * 1000.0
    content = response.content[0].text.strip() if response.content else ""

    # Strip possible markdown code fence
    if content.startswith("```"):
        lines = content.splitlines()
        inner = [ln for ln in lines if not ln.startswith("```")]
        content = "\n".join(inner).strip()

    parsed = json.loads(content)  # raises json.JSONDecodeError on bad response
    return parsed, latency_ms


def _safe_float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _passthrough(
    raw_input: str,
    skip_reason: str,
    latency_ms: float = 0.0,
) -> tuple[InterpretedInput, dict]:
    """Return an unmodified passthrough result with the given skip_reason."""
    result = InterpretedInput(
        normalized_text=raw_input,
        routing_hint=None,
        intent_hint=None,
        entity_hints={},
        confidence=0.0,
        debug_note=None,
        skipped=True,
        raw_input_seen=raw_input,
    )
    trace = {
        "raw_input_seen": raw_input,
        "normalized_text": raw_input,
        "normalized_text_used": False,
        "skipped": True,
        "skip_reason": skip_reason,
        "latency_ms": round(latency_ms, 1),
    }
    return result, trace


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


class InputInterpreter:
    """Narrow LLM-assisted input normalization.  Stateless and fail-safe."""

    def interpret(self, raw_input: str) -> tuple[InterpretedInput, dict]:
        """Normalize *raw_input* and return ``(InterpretedInput, trace_dict)``.

        The caller is responsible for attaching *trace_dict* to the debug trace
        under the key ``"interpreter_result"``.

        The returned ``InterpretedInput`` is always safe to use:
        - ``skipped=True``  → use ``raw_input`` unchanged.
        - ``confidence < _INTERPRETER_CONFIDENCE_THRESHOLD`` → use ``raw_input``.
        - Otherwise → use ``normalized_text``.

        No exception escapes this method.
        """
        # --- guard: disabled via env flag ---
        if _interpreter_disabled():
            return _passthrough(raw_input, "disabled")

        # --- guard: empty input ---
        stripped = raw_input.strip()
        if not stripped:
            return _passthrough(raw_input, "disabled")

        # --- Fix 3: "resume ... on <workspace>" → deterministic v1 normalization ---
        # Applied before the deterministic_match guard so that "resume work on JARVIS"
        # (which starts with the canonical "resume work" prefix) is caught here rather
        # than being skipped unchanged and failing the protocol trigger match.
        m = _RESUME_ON_PATTERN.search(stripped)
        if m:
            workspace = m.group(1).strip()
            if workspace:
                normalized = f"start work on {workspace}"
                result = InterpretedInput(
                    normalized_text=normalized,
                    routing_hint="command",
                    intent_hint="prepare_workspace",
                    entity_hints={"workspace": workspace},
                    confidence=1.0,
                    debug_note="resume…on pattern → start work on (deterministic v1 rule, no LLM)",
                    skipped=False,
                    raw_input_seen=raw_input,
                )
                trace = {
                    "raw_input_seen": raw_input,
                    "normalized_text": normalized,
                    "normalized_text_used": True,
                    "routing_hint": "command",
                    "routing_hint_used": True,
                    "intent_hint": "prepare_workspace",
                    "entity_hints": {"workspace": workspace},
                    "confidence": 1.0,
                    "debug_note": "resume…on pattern → start work on (deterministic v1 rule, no LLM)",
                    "skipped": False,
                    "skip_reason": None,
                    "latency_ms": 0.0,
                }
                return result, trace

        # --- fast-path: input is obviously terminal or a clear question ---
        # LLM-first: only bypass for inputs where normalization adds zero value.
        # All command-like inputs — including exact canonical ones — go through the LLM.
        if _is_obvious_fast_path(stripped):
            return _passthrough(raw_input, "fast_path")

        # --- LLM call with full fallback coverage ---
        t0 = time.monotonic()
        try:
            parsed, latency_ms = _call_llm(stripped)
        except TimeoutError:
            return _passthrough(raw_input, "timeout", (time.monotonic() - t0) * 1000.0)
        except Exception as exc:  # noqa: BLE001 — intentional broad catch
            exc_name = type(exc).__name__
            if "timeout" in exc_name.lower() or "timeout" in str(exc).lower():
                return _passthrough(raw_input, "timeout", (time.monotonic() - t0) * 1000.0)
            return _passthrough(raw_input, "api_error", (time.monotonic() - t0) * 1000.0)

        # --- parse and validate LLM response ---
        if not isinstance(parsed, dict):
            return _passthrough(raw_input, "malformed_response", latency_ms)

        normalized_text = str(parsed.get("normalized_text") or "").strip()
        routing_hint = str(parsed.get("routing_hint") or "").strip().lower() or None
        intent_hint = str(parsed.get("intent_hint") or "").strip() or None
        raw_entity_hints = parsed.get("entity_hints") or {}
        confidence = _safe_float(parsed.get("confidence", 0.0))
        debug_note = str(parsed.get("debug_note") or "").strip() or None

        if not isinstance(raw_entity_hints, dict):
            raw_entity_hints = {}

        # Normalize routing_hint to allowed values
        if routing_hint not in {"command", "question", "unclear", None}:
            routing_hint = None

        # --- safety boundary 1: questions must never become commands ---
        if _is_question_input(stripped) and routing_hint == "command":
            result = InterpretedInput(
                normalized_text=raw_input,
                routing_hint=None,
                intent_hint=None,
                entity_hints={},
                confidence=0.0,
                debug_note=debug_note,
                skipped=True,
                raw_input_seen=raw_input,
            )
            trace = {
                "raw_input_seen": raw_input,
                "normalized_text": normalized_text,
                "normalized_text_used": False,
                "routing_hint": routing_hint,
                "routing_hint_used": False,
                "intent_hint": intent_hint,
                "entity_hints": {},
                "confidence": round(confidence, 3),
                "debug_note": debug_note,
                "skipped": True,
                "skip_reason": "question_command_conflict",
                "latency_ms": round(latency_ms, 1),
            }
            return result, trace

        # --- safety boundary 4: unclear → discard interpreter output entirely ---
        if routing_hint == "unclear":
            return _passthrough(raw_input, "unclear", latency_ms)

        # --- safety boundary 3: low confidence → don't use normalized_text ---
        if confidence < _INTERPRETER_CONFIDENCE_THRESHOLD:
            result = InterpretedInput(
                normalized_text=raw_input,
                routing_hint=routing_hint,
                intent_hint=intent_hint,
                entity_hints={},
                confidence=confidence,
                debug_note=debug_note,
                skipped=True,
                raw_input_seen=raw_input,
            )
            trace = {
                "raw_input_seen": raw_input,
                "normalized_text": normalized_text,
                "normalized_text_used": False,
                "routing_hint": routing_hint,
                "routing_hint_used": False,
                "intent_hint": intent_hint,
                "entity_hints": {},
                "confidence": round(confidence, 3),
                "debug_note": debug_note,
                "skipped": True,
                "skip_reason": "low_confidence",
                "latency_ms": round(latency_ms, 1),
            }
            return result, trace

        # --- guard: normalized_text is empty or too long ---
        if not normalized_text or len(normalized_text) > _INTERPRETER_MAX_LENGTH_MULTIPLIER * len(stripped):
            return _passthrough(raw_input, "malformed_response", latency_ms)

        # --- safety boundary 2: entity grounding check ---
        entity_hints_raw = {k: str(v).strip() for k, v in raw_entity_hints.items() if str(v).strip()}
        entity_hints = _ground_entities(entity_hints_raw, stripped)
        entity_grounding_failed = bool(entity_hints_raw) and not entity_hints and bool(normalized_text != stripped)

        if entity_grounding_failed:
            result = InterpretedInput(
                normalized_text=raw_input,
                routing_hint=routing_hint,
                intent_hint=intent_hint,
                entity_hints={},
                confidence=0.0,
                debug_note=debug_note,
                skipped=True,
                raw_input_seen=raw_input,
            )
            trace = {
                "raw_input_seen": raw_input,
                "normalized_text": normalized_text,
                "normalized_text_used": False,
                "routing_hint": routing_hint,
                "routing_hint_used": False,
                "intent_hint": intent_hint,
                "entity_hints": {},
                "confidence": round(confidence, 3),
                "debug_note": debug_note,
                "skipped": True,
                "skip_reason": "entity_grounding_failed",
                "latency_ms": round(latency_ms, 1),
            }
            return result, trace

        # --- success path: interpreter result accepted ---
        normalized_text_used = normalized_text != stripped
        routing_hint_used = routing_hint is not None

        result = InterpretedInput(
            normalized_text=normalized_text,
            routing_hint=routing_hint,
            intent_hint=intent_hint,
            entity_hints=entity_hints,
            confidence=confidence,
            debug_note=debug_note,
            skipped=False,
            raw_input_seen=raw_input,
        )
        trace = {
            "raw_input_seen": raw_input,
            "normalized_text": normalized_text,
            "normalized_text_used": normalized_text_used,
            "routing_hint": routing_hint,
            "routing_hint_used": routing_hint_used,
            "intent_hint": intent_hint,
            "entity_hints": entity_hints,
            "confidence": round(confidence, 3),
            "debug_note": debug_note,
            "skipped": False,
            "skip_reason": None,
            "latency_ms": round(latency_ms, 1),
        }
        return result, trace
