# JARVIS MVP Use Cases

## Principles
- Repeatable: each use case should run the same way under the same inputs.
- Clear: user intent, system actions, and outcomes must be explicit.
- Executable with current system: all steps must fit supervised desktop control in MVP.
- Valuable in real daily workflows: each use case should save concrete user effort.

## Use Case Format
Each use case in this document uses the same template:
- `User Intent`: what the user wants in plain language.
- `Example Command`: realistic commands a user may type or say.
- `System Behavior`: explicit step-by-step behavior, including clarification and confirmation points.
- `Execution Notes`: edge cases, ambiguity handling, and safety limits.

### Use Case 1: Open Applications

**User Intent**  
Open one or more desktop applications (for example, Telegram and Safari).

**Example Command**  
- "Open Telegram and Safari."
- "Launch Telegram plus Safari."

**System Behavior**  
1. JARVIS understands an `open applications` intent with targets `Telegram` and `Safari`.
2. JARVIS checks whether each target app is installed and whether it is already running.
3. JARVIS opens apps that are closed and focuses apps that are already open.
4. If an app name is ambiguous, JARVIS asks a short clarification before acting on that target.
5. No confirmation is required for this safe action.

**Execution Notes**
- If one app is found and another is not, JARVIS executes only the found app and reports the missing one.
- JARVIS must not install software or use hidden fallback actions.
- Execution remains visible and interruptible.

### Use Case 2: Open File / Folder

**User Intent**  
Open a known file or folder (for example, the JARVIS project folder).

**Example Command**  
- "Open my JARVIS project folder."
- "Open /Users/arseniyabramidze/JARVIS."

**System Behavior**  
1. JARVIS understands an `open file/folder` intent with a path or name target.
2. JARVIS resolves the target location from explicit path or local search.
3. JARVIS opens the resolved folder/file in the default desktop app.
4. If multiple matches exist, JARVIS asks which one to open.
5. No confirmation is required for this safe action.

**Execution Notes**
- If no target is found, JARVIS stops and reports failure clearly.
- JARVIS must not move, rename, or delete files in this flow.
- JARVIS should prefer exact path matches over fuzzy name matches.

### Use Case 3: Workspace Setup

**User Intent**  
Prepare a simple working environment for JARVIS development.

**Example Command**  
- "Set up JARVIS workspace."
- "Open VS Code with the JARVIS folder and open Safari."

**System Behavior**  
1. JARVIS understands a `prepare workspace` intent with steps: open IDE, open project folder, open browser.
2. JARVIS shows a short visible plan before execution.
3. JARVIS executes steps one by one (open IDE, open folder, open browser).
4. If IDE or browser target is unclear, JARVIS asks a brief clarification.
5. No confirmation is required unless a later step becomes sensitive (not expected in this use case).

**Execution Notes**
- This use case is bounded to a short sequence and does not continue in background.
- If a step fails, JARVIS stops and reports which step failed.
- JARVIS must not run project commands or external integrations automatically.

### Use Case 4: Window Management

**User Intent**  
Close everything except one app (for example, keep VS Code open).

**Example Command**  
- "Close everything except VS Code."
- "Keep VS Code and close the rest."

**System Behavior**  
1. JARVIS understands a `window management` intent with keep-target `VS Code`.
2. JARVIS identifies currently open apps/windows that would be closed.
3. JARVIS presents a confirmation request with action description and affected targets.
4. JARVIS executes closes only after explicit user confirmation.
5. If system prompts show unsaved changes, JARVIS pauses and waits for user decision.

**Execution Notes**
- Confirmation is mandatory because closing windows can be destructive or irreversible.
- If VS Code is not open, JARVIS asks whether to open it first or stop.
- JARVIS must not force-close windows silently.

### Use Case 5: Search and Open

**User Intent**  
Find the latest markdown file and open it.

**Example Command**  
- "Find the latest markdown file and open it."
- "Open the newest .md file in this project."

**System Behavior**  
1. JARVIS understands a `search and open` intent with filter `*.md` and sort `latest`.
2. JARVIS determines search scope from context (for example, current project folder).
3. If scope is unclear, JARVIS asks a short clarification question.
4. JARVIS finds the best match and opens the file.
5. No confirmation is required for opening the selected file.

**Execution Notes**
- If multiple files tie as latest, JARVIS asks the user to choose.
- If no markdown files exist in scope, JARVIS stops and reports no match.
- JARVIS must not edit files in this use case.

### Use Case 6: Clarification Flow

**User Intent**  
Open a target when multiple matching files or apps exist.

**Example Command**  
- "Open notes."
- "Open Chrome."

**System Behavior**  
1. JARVIS understands an `open` intent but detects multiple valid matches.
2. JARVIS asks one minimal clarification question listing clear options.
3. JARVIS waits for user answer and performs no action until clarified.
4. JARVIS executes only the selected option.
5. Confirmation is requested only if the resulting action is sensitive.

**Execution Notes**
- Clarification should be short and specific (for example, "Which notes file: `notes.md` or `meeting-notes.md`?").
- JARVIS must never guess silently when ambiguity exists.
- If user response is still ambiguous, JARVIS asks again with narrower options.

### Use Case 7: Safe Failure Case

**User Intent**  
Open an app or file that does not exist on the device.

**Example Command**  
- "Open SuperEditor."
- "Open file roadmap-final-v9.md."

**System Behavior**  
1. JARVIS understands the open intent and attempts target resolution in allowed local scope.
2. If not found, JARVIS stops execution immediately.
3. JARVIS reports exactly what was not found.
4. JARVIS suggests a next action (for example, check spelling or provide path).
5. JARVIS does not retry in background and does not perform hidden alternatives.

**Execution Notes**
- No hidden retries, no autonomous download/install, and no external lookup.
- Failure response must be concise and actionable.
- If partial matches exist, JARVIS may suggest them but must not auto-open.

### Use Case 8: Context Follow-up

**User Intent**  
Issue a short follow-up command that depends on the current session context.

**Example Command**  
- "Now open browser too."
- "Also open Telegram."

**System Behavior**  
1. JARVIS understands a follow-up intent using current active task context.
2. JARVIS resolves omitted details from immediate session state (for example, workspace setup in progress).
3. If context is insufficient (for example, no browser preference), JARVIS asks a short clarification.
4. JARVIS executes the additional safe step visibly.
5. No confirmation is required unless the follow-up action is sensitive.

**Execution Notes**
- Context use is limited to the active supervised session.
- JARVIS must not assume long-term memory or background continuation.
- If follow-up conflicts with prior instruction, JARVIS asks before proceeding.
