# JARVIS MVP Manual Verification Commands

## Purpose
- Provide a deterministic local CLI checklist for supervised release verification.
- Keep checks inside current MVP action surface and blocked-state rules.

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

### 8) Voice failure diagnostics
- Input: `voice` (with voice helper unavailable/denied path)
- Expected: concise structured diagnostic with actionable hint (no generic `Voice capture failed.` output).
