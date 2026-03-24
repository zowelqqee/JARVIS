# JARVIS MVP Manual Verification Commands

## Purpose
- Provide one dual-mode local CLI checklist for supervised release verification.
- Keep checks inside the current command runtime and grounded QA surface.

## Run
- `python3 cli.py`

## Command Set

### 1) Open app alias
- Input: `run telegram`
- Expected: `open_app` execution path (or explicit `APP_UNAVAILABLE`), no clarification loop.

### 2) Clarification resume
- Input: `htlp`
- Expected: `awaiting_clarification`
- Follow-up: `open Safari`
- Expected: fresh command restart and normal execution path.

### 3) Confirmation approve/deny
- Input: `close Telegram`
- Expected: `awaiting_confirmation`
- Follow-up: `yes`
- Expected: execution continues from boundary.
- Repeat with `no`
- Expected: `cancelled`, blocked step not executed.

### 4) Search + indexed follow-up
- Input: `search the JARVIS folder for markdown files`
- Expected: completed search with visible results.
- Follow-up: `open 1`
- Expected: deterministic file-open follow-up path.

### 5) Workspace path resolution
- Input: `prepare workspace for JARVIS`
- Expected: folder target includes current project path; either executes or fails explicitly by app availability.

### 6) Window listing
- Input: `list windows`
- Expected: real window list on supported session, or explicit failure with no fake data.

### 7) Shell command separation
- Input: `help`, `voice`, `speak on`, `speak off`, `reset`, `quit`
- Expected: intercepted by CLI shell layer before runtime parsing.

### 8) QA helper commands
- Input: `qa backend`, `qa model`, `qa smoke`
- Expected: intercepted by CLI shell layer; print QA backend/model/live-smoke readiness without mutating runtime state.

### 9) Capability question
- Input: `what can you do?`
- Expected: `mode: question` with grounded answer, source labels, and raw paths; no execution steps.

### 10) Documentation question + safe follow-ups
- Input: `how does clarification work?`
- Expected: grounded answer from local docs.
- Follow-up: `explain more`
- Expected: more detailed grounded answer, still read-only.
- Follow-up: `which source?`
- Expected: source-focused answer that reuses the recent answer source bundle.

### 11) Blocked-state question
- Input: `close Telegram`
- Expected: `awaiting_confirmation`
- Follow-up: `what exactly do you need me to confirm?`
- Expected: `mode: question`, read-only explanation of the current confirmation boundary.

### 12) Recent-runtime question
- Input: `open Safari`
- Follow-up: `what command did you run last?`
- Expected: `mode: question`, answer grounded in visible runtime/session context.

### 13) Mixed question + action routing
- Input: `what can you do and open Safari`
- Expected: routing clarification only; no silent answer+execute behavior.

### 14) Voice failure diagnostics
- Input: `voice` (with voice helper unavailable/denied path)
- Expected: concise structured diagnostic with actionable hint (no generic `Voice capture failed.` output).

### 15) Live OpenAI smoke
- Command: `scripts/run_openai_live_smoke.sh`
- Expected: only run when `OPENAI_API_KEY` is present and the environment is intended for live provider verification.
- Expected output: live smoke prints provider, model, source count, and whether deterministic fallback happened.
