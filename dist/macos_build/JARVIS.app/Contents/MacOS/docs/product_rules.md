# JARVIS Product Rules (MVP)

## Product Definition
JARVIS is a supervised desktop assistant with two top-level interaction modes:
- `command mode`: understand natural language commands and perform desktop actions clearly, safely, and under user control.
- `question-answer mode`: answer user questions without executing actions.

Current shipped/default question-answer path:
- grounded local answers about capabilities, current runtime state, documented behavior, and repository structure
- explicit local sources for grounded answers

Planned next expansion:
- broader GPT-backed answers for open-domain user questions
- still read-only
- still visibly separate from `command` mode
- still required to expose truthful provenance and safety boundaries

JARVIS remains desktop-focused. A broader question-answer surface does not change that positioning, and it does not create autonomous background workflows.
JARVIS executes only explicit user commands and does not initiate actions independently.
JARVIS does not persist long-running workflows in MVP.

## Core Principles
1. Single active task: JARVIS handles one active command task at a time.
2. Full visibility: JARVIS shows step-by-step execution as it works and exposes answers with truthful provenance.
3. Explicit confirmation for risk: JARVIS asks before sensitive actions.
4. No hidden actions: JARVIS does not execute invisible or silent operations.
5. User control at all times: the user can confirm, redirect, or stop actions at any point.
6. Answering is read-only: question-answer mode must not execute actions.
7. Grounded answers stay grounded: local-source answers must not guess beyond allowed sources.
8. Model answers stay labeled: broader model-knowledge answers must not pretend to come from local docs/runtime sources.

## Non-Goals (MVP)
- No autonomous task execution
- No background agents
- No multi-step long workflows across many systems
- No payments, authentication, or sensitive data handling
- No hidden "assistant for everything" behavior that bypasses desktop-product boundaries
- No internet-backed general Q&A by default
- No fabricated citations or fake local grounding for model answers

## Desktop Execution
### MVP scope
- Applications
- Files and folders
- Browser
- Windows

### Typical actions
- Open, close, and switch between apps and windows
- Search for files, folders, pages, or tabs
- Prepare workspace by opening the needed apps, folders, and browser pages
- Run named protocols by expanding them into visible supervised steps

### Execution Model
- JARVIS translates command intent into a sequence of explicit steps.
- Each step must be observable, interruptible, and reversible where possible.
- Execution must stop on ambiguity.
- Execution must stop on missing data.
- Execution must stop on sensitive action requiring confirmation.

### Execution boundaries
- No sensitive operation is performed without explicit confirmation.
- No background autonomous execution is allowed.
- Question-answer mode must not cross into execution.

## Interaction Model
JARVIS receives one natural-language input and routes it into one of two top-level paths:
1. `command`
2. `question`

Routing rules:
- blocked confirmation/clarification replies for an active command take precedence
- explicit action requests route to command mode
- explicit questions route to question-answer mode
- mixed or unclear requests trigger one short clarification

Future-ready rule:
- broader GPT answering may widen what happens inside question mode
- it must not change top-level routing precedence
- it must not let question mode silently capture execution requests

### Command mode
JARVIS converts natural language into a structured executable intent and runs only what is clear and in scope.

Each command must resolve to:
- intent (action type)
- target (app/file/window/etc.)
- parameters (optional)
- confidence level
- requires_confirmation (boolean)

If confidence is low, JARVIS must not execute and must ask for clarification.

### Question-answer mode
Question-answer mode is read-only.
Current shipped/default path may answer only from grounded sources such as:
- repository docs
- explicit capability metadata
- current runtime state
- active session context

Planned broader path may answer open-domain questions through GPT, but only when that rollout is explicitly enabled and only with truthful model-knowledge provenance.

Architecture rule:
- default v1 product path uses deterministic answer generation
- an opt-in model-backed answer backend may exist behind the same answer contract
- a later broader GPT answer path may exist behind the same top-level `question` mode
- backend choice must not change routing, confirmation, grounding, or execution boundaries

Question-answer mode must not:
- execute actions
- imply confirmation
- hide missing grounding
- pretend model knowledge came from local docs/runtime state
- answer mixed action requests without clarification

## Safety Model
JARVIS uses two action classes.

### Safe actions (can run without confirmation)
- Open app
- Switch window
- Search for file
- Open folder
- Prepare workspace (open and arrange required apps/windows without destructive changes)

### Sensitive actions (require explicit confirmation)
- Delete or move files
- Submit forms
- Send messages or emails
- Change settings
- Close work with possible unsaved changes
- Download or install software

For sensitive actions, JARVIS must state what it is about to do and wait for user confirmation before continuing.
JARVIS must never execute destructive or irreversible actions without confirmation, even if confidence is high.
Every confirmation must include:
- action description
- affected target

## Response Modes
For each interaction, JARVIS must respond in one of these visible modes:
- answer
- plan
- execution update
- clarification
- confirmation request

Rules:
- `answer` is read-only.
- grounded local answers must remain source-backed.
- broader model-backed answers must stay explicitly labeled as model knowledge when that path is enabled.
- `plan`, `execution update`, and `confirmation request` belong to command mode.
- `clarification` may be used to resolve either command ambiguity or question/command routing ambiguity.
- No silent execution is allowed.
- No long explanations.
- Communication style must stay concise, human, and clear.

## MVP Interaction Lifecycle
1. User input
2. Route interaction
3. If command -> parse + validate intent
4. If unclear -> clarification
5. If command -> show short execution plan
6. If command -> execute step-by-step (visible)
7. If command and sensitive -> confirmation
8. If question -> build the configured read-only answer path
9. Return result and remain ready for next input

## Failure Handling
- If a command step fails, stop execution.
- Explain what failed.
- Suggest next action.
- Do not continue blindly.
- If a grounded local question cannot be answered from allowed local sources, fail honestly and do not guess.
- If a broader model-backed question path is unavailable, unsafe, or out of policy, fail honestly instead of fabricating authority.

See also:
- `docs/question_answer_mode.md`
- `docs/general_qa_policy.md`
