# JARVIS Clarification Rules (Dual-Mode MVP)

## Purpose
Define how JARVIS responds when an interaction cannot continue safely due to ambiguity, missing data, low confidence, or unresolved routing between command mode and question-answer mode.

## When Clarification Is Required
JARVIS must ask for clarification and must not execute when:
- confidence is below threshold
- multiple valid command targets exist
- no valid command target is found
- required command parameters are missing
- command intent is unclear or partially parsed
- follow-up reference cannot be resolved from session context
- one input mixes question and command semantics without a clear routing decision
- routing between `command` and `question` cannot be resolved deterministically

Clarification is a hard boundary. Execution must remain blocked until clarification is resolved.
Question-answer mode must not silently take over a mixed request just because execution is blocked.

## Clarification Principles
- always ask the minimal question needed to proceed
- never ask multiple questions at once
- never ask vague or open-ended questions
- always tie the question to a concrete next decision
- do not restate the entire input

## Clarification Types
### Target ambiguity
Example: "Open notes"

Behavior:
- detect multiple matching files or apps
- ask: "Which one do you mean: notes.md or meeting-notes.md?"

### Missing parameter
Example: "Search files"

Behavior:
- detect missing query or scope
- ask: "What should I search for?"

### No match
Example: "Open SuperEditor"

Behavior:
- detect no valid target
- ask or suggest: "I couldn't find SuperEditor. Did you mean one of these?"

### Follow-up ambiguity
Example: "Close that one"

Behavior:
- if multiple recent targets exist, ask: "Which one should I close?"

### Low confidence
Example: unclear or noisy input

Behavior:
- do not execute
- ask for rephrase or confirmation: "I'm not sure what you meant. Can you rephrase?"

### Routing ambiguity
Example: "What can you do and open Safari"

Behavior:
- detect mixed question and action semantics
- ask one short routing question such as: "Do you want an answer first or should I open Safari?"
- do not both answer and execute in one silent pass

## Clarification Response Format
Each clarification must:
- be one sentence
- include concrete options when possible
- avoid technical language
- map directly to a resolvable next step or routing decision

Allowed:
- short list of options
- direct question

Not allowed:
- long explanations
- multiple questions
- speculative guesses

## After Clarification
1. resolve ambiguity
2. update blocked command or blocked routing choice
3. continue from the blocked point

Rules:
- do not restart the full command unnecessarily
- do not lose already completed steps
- do not re-ask the same clarification
- do not auto-execute after a routing clarification unless command intent is explicit

## Clarification Failure
If the user response is still unclear:
- ask again with narrower options
- reduce ambiguity space

If repeated failure continues:
- stop execution or stop answer attempt
- suggest explicit input format

No loops without progress. No hidden fallback execution.

## Constraints
- No automatic guessing
- No silent fallback actions
- No execution before clarification is resolved
- No chaining multiple clarifications at once
- No silent answer-plus-execute behavior
