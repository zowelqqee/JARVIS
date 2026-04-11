# JARVIS Dual-Mode Use Cases

## Principles
- Repeatable: each use case should run the same way under the same inputs.
- Clear: user intent, system actions, and outcomes must be explicit.
- Safe: execution must stay supervised and answers must stay grounded.
- Valuable in real daily workflows: each use case should save concrete user effort or answer a concrete question.

## Use Case Format
Each use case in this document uses the same template:
- `User Intent`: what the user wants in plain language.
- `Example Input`: realistic commands or questions a user may type or say.
- `System Behavior`: explicit step-by-step behavior, including clarification and confirmation points.
- `Notes`: edge cases, ambiguity handling, safety limits, or grounding limits.

### Use Case 1: Open Applications

**User Intent**  
Open one or more desktop applications (for example, Telegram and Safari).

**Example Input**  
- "Open Telegram and Safari."
- "Launch Telegram plus Safari."

**System Behavior**  
1. JARVIS routes the input to command mode.
2. JARVIS understands an `open applications` intent with targets `Telegram` and `Safari`.
3. JARVIS checks whether each target app is installed and whether it is already running.
4. JARVIS opens apps that are closed and focuses apps that are already open.
5. If an app name is ambiguous, JARVIS asks a short clarification before acting on that target.
6. No confirmation is required for this safe action.

**Notes**
- If one app is found and another is not, JARVIS executes only the found app and reports the missing one.
- JARVIS must not install software or use hidden fallback actions.
- Execution remains visible and interruptible.

### Use Case 2: Open File / Folder

**User Intent**  
Open a known file or folder (for example, the JARVIS project folder).

**Example Input**  
- "Open my JARVIS project folder."
- "Open /Users/arseniyabramidze/JARVIS."

**System Behavior**  
1. JARVIS routes the input to command mode.
2. JARVIS understands an `open file/folder` intent with a path or name target.
3. JARVIS resolves the target location from explicit path or local search.
4. JARVIS opens the resolved folder/file in the default desktop app.
5. If multiple matches exist, JARVIS asks which one to open.
6. No confirmation is required for this safe action.

**Notes**
- If no target is found, JARVIS stops and reports failure clearly.
- JARVIS must not move, rename, or delete files in this flow.
- JARVIS should prefer exact path matches over fuzzy name matches.

### Use Case 3: Workspace Setup

**User Intent**  
Prepare a simple working environment for JARVIS development.

**Example Input**  
- "Set up JARVIS workspace."
- "Open VS Code with the JARVIS folder and open Safari."

**System Behavior**  
1. JARVIS routes the input to command mode.
2. JARVIS understands a `prepare workspace` intent with steps: open IDE, open project folder, open browser.
3. JARVIS shows a short visible plan before execution.
4. JARVIS executes steps one by one (open IDE, open folder, open browser).
5. If IDE or browser target is unclear, JARVIS asks a brief clarification.
6. No confirmation is required unless a later step becomes sensitive.

**Notes**
- This use case is bounded to a short sequence and does not continue in background.
- If a step fails, JARVIS stops and reports which step failed.
- JARVIS must not run project commands or external integrations automatically.

### Use Case 4: Window Management

**User Intent**  
Close everything except one app (for example, keep VS Code open).

**Example Input**  
- "Close everything except VS Code."
- "Keep VS Code and close the rest."

**System Behavior**  
1. JARVIS routes the input to command mode.
2. JARVIS understands a window-management request with keep-target `VS Code`.
3. If the exact batch behavior is unsupported, JARVIS fails honestly as unsupported instead of pretending to execute.
4. If a supported close path is available, JARVIS presents a confirmation request with action description and affected targets.
5. JARVIS executes closes only after explicit user confirmation.
6. If system prompts show unsaved changes, JARVIS pauses and waits for user decision.

**Notes**
- Confirmation is mandatory because closing windows can be destructive or irreversible.
- JARVIS must not force-close windows silently.
- Unsupported window-management forms must remain explicit and honest.

### Use Case 5: Search and Open

**User Intent**  
Find the latest markdown file and open it.

**Example Input**  
- "Find the latest markdown file and open it."
- "Open the newest .md file in this project."

**System Behavior**  
1. JARVIS routes the input to command mode.
2. JARVIS understands a `search and open` intent with filter `*.md` and sort `latest`.
3. JARVIS determines search scope from context (for example, current project folder).
4. If scope is unclear, JARVIS asks a short clarification question.
5. JARVIS finds the best match and opens the file.
6. No confirmation is required for opening the selected file.

**Notes**
- If multiple files tie as latest, JARVIS asks the user to choose.
- If no markdown files exist in scope, JARVIS stops and reports no match.
- JARVIS must not edit files in this use case.

### Use Case 6: Clarification Flow

**User Intent**  
Open a target when multiple matching files or apps exist.

**Example Input**  
- "Open notes."
- "Open Chrome."

**System Behavior**  
1. JARVIS routes the input to command mode.
2. JARVIS understands an `open` intent but detects multiple valid matches.
3. JARVIS asks one minimal clarification question listing clear options.
4. JARVIS waits for user answer and performs no action until clarified.
5. JARVIS executes only the selected option.
6. Confirmation is requested only if the resulting action is sensitive.

**Notes**
- Clarification should be short and specific (for example, "Which notes file: `notes.md` or `meeting-notes.md`?").
- JARVIS must never guess silently when ambiguity exists.
- If user response is still ambiguous, JARVIS asks again with narrower options.

### Use Case 7: Safe Failure Case

**User Intent**  
Open an app or file that does not exist on the device.

**Example Input**  
- "Open SuperEditor."
- "Open file roadmap-final-v9.md."

**System Behavior**  
1. JARVIS routes the input to command mode.
2. JARVIS understands the open intent and attempts target resolution in allowed local scope.
3. If not found, JARVIS stops execution immediately.
4. JARVIS reports exactly what was not found.
5. JARVIS suggests a next action (for example, check spelling or provide path).
6. JARVIS does not retry in background and does not perform hidden alternatives.

**Notes**
- No hidden retries, no autonomous download/install, and no external lookup.
- Failure response must be concise and actionable.
- If partial matches exist, JARVIS may suggest them but must not auto-open.

### Use Case 8: Context Follow-up

**User Intent**  
Issue a short follow-up command that depends on the current session context.

**Example Input**  
- "Now open browser too."
- "Also open Telegram."

**System Behavior**  
1. JARVIS routes the input to command mode.
2. JARVIS understands a follow-up intent using current active task context.
3. JARVIS resolves omitted details from immediate session state (for example, workspace setup in progress).
4. If context is insufficient (for example, no browser preference), JARVIS asks a short clarification.
5. JARVIS executes the additional safe step visibly.
6. No confirmation is required unless the follow-up action is sensitive.

**Notes**
- Context use is limited to the active supervised session.
- JARVIS must not assume long-term memory or background continuation.
- If follow-up conflicts with prior instruction, JARVIS asks before proceeding.

### Use Case 9: Capability Question

**User Intent**  
Ask what JARVIS can do without requesting execution.

**Example Input**  
- "What can you do?"
- "Which commands do you support?"

**System Behavior**  
1. JARVIS routes the input to question-answer mode.
2. JARVIS classifies the question as `capabilities`.
3. JARVIS grounds the answer in capability metadata and product/docs rules.
4. JARVIS returns a concise answer listing supported action families and major limits.
5. JARVIS does not create an execution plan and does not run anything.

**Notes**
- The answer should mention major supported actions and major non-goals.
- If capability data is unavailable, JARVIS fails honestly instead of guessing.
- Question mode remains read-only.

### Use Case 10: Runtime Status Question

**User Intent**  
Ask what JARVIS is doing now or why it is blocked.

**Example Input**  
- "What are you doing now?"
- "Why are you waiting?"

**System Behavior**  
1. JARVIS routes the input to question-answer mode unless an explicit blocked-state reply takes precedence.
2. JARVIS classifies the question as `runtime_status`.
3. JARVIS grounds the answer in current runtime visibility and session context.
4. JARVIS returns the current command summary, blocked reason, or current step when available.
5. JARVIS does not resume execution, approve confirmation, or alter blocked state.

**Notes**
- If no active command context exists, JARVIS should say so directly.
- Runtime status answers must describe only visible supervised state.
- Question mode must not act as a hidden control channel.

### Use Case 10A: Blocked-State Question

**User Intent**  
Ask what a currently blocked command needs without approving or resuming it.

**Example Input**  
- "What are you waiting for?"
- "What exactly do you need me to confirm?"

**System Behavior**  
1. If the active command is blocked, JARVIS routes the input to question-answer mode only when it is clearly asking about the blocked state.
2. JARVIS classifies the question as `blocked_state`.
3. JARVIS grounds the answer in current blocked runtime visibility plus clarification/confirmation rules.
4. JARVIS answers what confirmation or clarification is needed.
5. JARVIS does not resume execution and does not treat the question as approval.

**Notes**
- Confirmation replies such as "yes" or "cancel" still stay on the command path.
- Blocked-state questions must stay read-only.
- If no blocked command is active, JARVIS must fail honestly instead of inventing a reason.

### Use Case 10B: Recent Runtime Question

**User Intent**  
Ask about the most recent visible command or target from the current supervised session.

**Example Input**  
- "What command did you run last?"
- "What app did you open last?"

**System Behavior**  
1. JARVIS routes the input to question-answer mode.
2. JARVIS classifies the question as `recent_runtime`.
3. JARVIS reads only short-lived session/runtime context such as recent command summary, recent target, and recent workspace context.
4. JARVIS returns the most recent visible command or target when that context exists.
5. JARVIS does not search the repo or execute anything to answer.

**Notes**
- Recent-runtime answers are limited to the current supervised session.
- If no recent target or command is available, JARVIS must return bounded insufficient-context failure.
- This does not introduce long-term memory.

### Use Case 11: Documentation Question

**User Intent**  
Ask how a documented rule or subsystem works.

**Example Input**  
- "How does clarification work?"
- "Where does runtime state live?"

**System Behavior**  
1. JARVIS routes the input to question-answer mode.
2. JARVIS classifies the question as `docs_rules` or `repo_structure`.
3. JARVIS selects the smallest source set needed from local docs.
4. JARVIS returns a concise explanation grounded in those docs.
5. JARVIS includes the source files used to support the answer.

**Notes**
- The answer must stay within documented behavior.
- If the question reaches beyond supported doc scope, JARVIS must say that clearly.
- No code execution or hidden repo search outside the allowed grounded scope in v1.

### Use Case 12: Safety Explanation Question

**User Intent**  
Understand why a command requires confirmation or why JARVIS refused an action.

**Example Input**  
- "Why do you need confirmation for that?"
- "Why didn't you execute?"

**System Behavior**  
1. JARVIS routes the input to question-answer mode unless the input is actually a confirmation reply.
2. JARVIS classifies the question as `safety_explanations` or `runtime_status`.
3. JARVIS grounds the answer in safety rules and current visible runtime state.
4. JARVIS explains the relevant safety boundary briefly and concretely.
5. JARVIS does not weaken or bypass the existing confirmation/clarification boundary.

**Notes**
- If the user still wants execution, they must provide explicit command or confirmation input.
- The answer should be tied to the active blocked state when one exists.
- Safety explanations must not silently transform into approval.

### Use Case 13: Mixed Question + Action Request

**User Intent**  
Ask a question and request an action in one input.

**Example Input**  
- "What can you do and open Safari."
- "Why are you blocked and continue."

**System Behavior**  
1. JARVIS detects that the input mixes question and action semantics.
2. JARVIS does not both answer and execute in one silent pass.
3. JARVIS asks one short clarification to resolve whether the user wants an answer first or command execution first.
4. JARVIS waits for the user decision.
5. JARVIS proceeds only after routing ambiguity is resolved explicitly.

**Notes**
- Mixed requests are a routing ambiguity, not an opportunity for hidden multi-action behavior.
- Clarification must stay short and decision-oriented.
- No execution occurs before routing is resolved.

### Use Case 14: Safe Answer Follow-up

**User Intent**  
Ask for one more grounded detail about the most recent answer without changing execution state.

**Example Input**  
- "How does clarification work?" -> "Explain more"
- "Which source?"
- "Where is that written?"
- "Why?"

**System Behavior**  
1. JARVIS answers the first question in question-answer mode and stores only short-lived recent answer context: topic, scope, and cited sources.
2. A follow-up such as "Explain more" or "Which source?" routes to question-answer mode only if it clearly refers to that recent answer.
3. JARVIS reuses the recent grounded source bundle instead of silently selecting new unrelated sources.
4. JARVIS returns a more detailed explanation, source list, or bounded why-answer grounded in that same answer context.
5. JARVIS does not execute anything and does not mutate command runtime state.

**Notes**
- If no recent grounded answer context exists, JARVIS must fail honestly with insufficient context.
- Safe answer follow-ups are session-scoped, not cross-session memory.
- Follow-up wording must not bypass command routing or trigger hidden execution.
