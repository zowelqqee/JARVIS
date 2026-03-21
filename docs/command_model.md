# JARVIS Command Model (MVP)

## Purpose
Define how natural language commands are transformed into structured execution instructions for JARVIS MVP desktop control.

The `Command` object is the strict contract between the parser and the execution engine.

## Command Flow
1. User input (text or voice -> text): receive user command as text.
2. Parsing (LLM or rule-based): extract intent, targets, and parameters.
3. Structured command object: build a `Command` object in the required shape.
4. Validation: enforce confidence, ambiguity, and required-parameter rules.
5. Execution planning: produce ordered `execution_steps` for validated command.
6. Execution: run steps sequentially with status updates and required pauses.

## Command Object (Core Structure)
```text
Command {
  raw_input: string,
  intent: string,
  targets: Target[],
  parameters: object,
  confidence: float (0–1),
  requires_confirmation: boolean,
  execution_steps: Step[],
  status_message: string
}
```

Field definitions:
- `raw_input`: original user text after voice-to-text normalization (if voice was used).
- `intent`: fixed MVP intent label produced by parser; must match the intent list in this document.
- `targets`: resolved entities the command acts on (apps, files, folders, windows, browser).
- `parameters`: optional execution modifiers (for example, search query, website URL, window filter).
- `confidence`: parser confidence score from `0` to `1`.
- `requires_confirmation`: command-level confirmation gate before execution starts.
- `execution_steps`: ordered list of executable desktop steps.
- `status_message`: concise user-facing state text (for example, "Opening VS Code", "Waiting for confirmation").

## Target Object
```text
Target {
  type: "application" | "file" | "folder" | "window" | "browser" | "unknown",
  name: string,
  path?: string,
  metadata?: object
}
```

Type usage:
- `application`: desktop app targets (for example, VS Code, Telegram).
- `file`: local file target.
- `folder`: local folder target.
- `window`: specific open window target.
- `browser`: browser app or browser window target.
- `unknown`: unresolved target that must be clarified before execution.

Field notes:
- `name` is required and used for matching/display.
- `path` is optional and used when known for file/folder targets.
- `metadata` is optional and minimal (for example, window id, bundle id, recency).
- No target categories beyond the listed `type` values are allowed in MVP.

## Step Object
```text
Step {
  id: string,
  action: string,
  target: Target,
  parameters?: object,
  status: "pending" | "executing" | "done" | "failed",
  requires_confirmation: boolean
}
```

Field definitions:
- `id`: unique step identifier within one command.
- `action`: concrete executable desktop action (for example, `open_app`, `focus_window`, `close_window`, `open_path`).
- `target`: single `Target` object the step operates on.
- `parameters`: optional action-specific inputs.
- `status`: runtime state for this step.
- `requires_confirmation`: pause gate before this step runs.

Step rules:
- Steps are executed sequentially in listed order.
- `action` must map directly to executable desktop behavior.
- Execution engine must not reorder steps.

## Intent Types (MVP)
Parser output must map to one of these fixed intents only. Dynamic intent creation is not allowed in MVP.

- `open_app`: open or focus a desktop application.
- `open_file`: open a local file.
- `open_folder`: open a local folder.
- `open_website`: open a URL in a browser.
- `switch_window`: focus a specific existing window.
- `close_window`: close one or more windows.
- `close_app`: close an application.
- `list_windows`: return currently open windows.
- `search_local`: search local files/folders by query.
- `prepare_workspace`: run a short predefined setup sequence (apps/folders/browser).
- `clarify`: ask the user for missing or ambiguous input.
- `confirm`: capture explicit user approval to continue.

## Command Validation Rules
Validation happens before execution planning and before execution.

1. If `confidence < CONFIDENCE_THRESHOLD`, command execution is blocked and JARVIS must ask clarification.
2. If targets are ambiguous, command execution is blocked and JARVIS must trigger clarification.
3. If required parameters are missing, command execution is blocked and JARVIS must ask the user for the missing values.
4. If intent is unknown or outside the fixed list, command execution is blocked and JARVIS must fallback to clarification.

## Confirmation Rules
Confirmation is mandatory for any command or step marked as requiring confirmation.

Command-level rules:
- If `requires_confirmation = true` on `Command`, JARVIS must pause before step 1.
- JARVIS must not execute any step until explicit user confirmation is received.

Step-level rules:
- If `requires_confirmation = true` on a `Step`, JARVIS must pause at that step.
- JARVIS may execute prior steps, but must not execute the gated step until explicit confirmation is received.

Confirmation message requirements:
- Include a clear description of the action.
- Include all affected targets.

MVP examples where confirmation is mandatory:
- Closing windows that may contain unsaved work.
- Closing applications that may terminate active work.

Implicit confirmation is not allowed.

## Ambiguity Handling
Ambiguity blocks execution.

- Multiple targets: ask user to choose one explicit target.
- No targets: ask a clarification question for missing target.
- Partial match: suggest closest options and ask user to pick.
- Never auto-select if ambiguity exists.

Clarification must be short, actionable, and tied to immediate next step.

## Execution Rules
- Execute `execution_steps` sequentially.
- Each step must update `status` (`pending` -> `executing` -> `done` or `failed`).
- Stop execution on failure.
- Stop execution on ambiguity.
- Stop execution when confirmation is required and not yet granted.
- Do not skip steps.
- Do not continue after failure.
- No parallel step execution.
- No hidden execution branches.

## Failure Rules
- Mark the current step as `failed`.
- Stop the entire command immediately.
- Return a concise failure report containing:
  - what failed
  - why it failed
  - suggested next action
- No autonomous retries.
- No hidden recovery behavior.

## Constraints
- No background execution.
- No multi-command batching.
- No autonomous retries.
- No hidden fallback actions.
