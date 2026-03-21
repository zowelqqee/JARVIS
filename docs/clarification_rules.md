# JARVIS Clarification Rules (MVP)

## Purpose
Define how JARVIS responds when a command cannot be executed safely due to ambiguity, missing data, or low confidence.

## When Clarification Is Required
JARVIS must ask for clarification and must not execute when:
- confidence is below threshold
- multiple valid targets exist
- no valid target is found
- required parameters are missing
- command intent is unclear or partially parsed
- follow-up reference cannot be resolved from session context

Clarification is a hard execution boundary. Execution must remain blocked until clarification is resolved.

## Clarification Principles
- always ask the minimal question needed to proceed
- never ask multiple questions at once
- never ask vague or open-ended questions
- always tie the question to a concrete next action
- do not restate the entire command

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

## Clarification Response Format
Each clarification must:
- be one sentence
- include concrete options when possible
- avoid technical language
- map directly to a resolvable next step

Allowed:
- short list of options
- direct question

Not allowed:
- long explanations
- multiple questions
- speculative guesses

## After Clarification
1. resolve ambiguity
2. update command or step
3. continue execution from blocked point

Rules:
- do not restart the full command unnecessarily
- do not lose already completed steps
- do not re-ask the same clarification

## Clarification Failure
If the user response is still unclear:
- ask again with narrower options
- reduce ambiguity space

If repeated failure continues:
- stop execution
- suggest explicit command format

No loops without progress. No hidden fallback execution.

## Constraints
- No automatic guessing
- No silent fallback actions
- No execution before clarification is resolved
- No chaining multiple clarifications at once
