# JARVIS Desktop Actions (MVP)

## Purpose
Define the fixed set of desktop actions that the MVP executor may perform.

- Actions are the only executable units in MVP.
- Every `Step.action` must map to one action in this document.
- Unsupported actions must fail explicitly with `unsupported_action`.

## Action Contract Format
Use this exact contract for every action definition in this document.

### Action: [action_name]

**Purpose**  
Short description of what the action does.

**Allowed targets**  
What `Target.type` values this action supports.

**Required inputs**  
What fields or parameters must exist before execution.

**Execution result**  
What success returns.

**Failure cases**  
What can fail and how it should be reported.

**Confirmation rule**  
Whether confirmation is never required / sometimes required / always required.

**Notes**  
Scope limits and safety boundaries.

## Required Actions
1. `open_app`
2. `focus_app`
3. `open_file`
4. `open_folder`
5. `open_website`
6. `list_windows`
7. `focus_window`
8. `close_window`
9. `close_app`
10. `search_local`
11. `prepare_workspace`
12. `play_music`

## Action Definitions
### Action: open_app

**Purpose**  
Open an installed application, or focus it if it is already running.

**Allowed targets**  
- `application`

**Required inputs**  
- `target.type = "application"`
- `target.name` resolved to one installed app

**Execution result**  
- `success = true`
- app is running and focused
- `details` may include `{ opened: boolean, focused: true }`

**Failure cases**  
- `target_not_found`: app cannot be resolved or is not installed
- `target_ambiguous`: multiple app matches
- `permission_denied`: OS denied launch/focus request
- `unsupported_target_type`: non-`application` target provided

**Confirmation rule**  
Never required.

**Notes**  
No install behavior. No app settings changes.

### Action: focus_app

**Purpose**  
Bring a running application to the foreground.

**Allowed targets**  
- `application`

**Required inputs**  
- `target.type = "application"`
- `target.name` resolved to one running app

**Execution result**  
- `success = true`
- target app is foreground-focused

**Failure cases**  
- `app_not_running`: target app is not currently running
- `target_not_found`: app target cannot be resolved
- `target_ambiguous`: multiple app matches
- `permission_denied`: OS denied focus request

**Confirmation rule**  
Never required.

**Notes**  
Does not launch missing apps.

### Action: open_file

**Purpose**  
Open a local file in the default app, or a specified app if already resolved by command input.

**Allowed targets**  
- `file`

**Required inputs**  
- `target.type = "file"`
- resolved `target.path`
- optional resolved `parameters.app` if command already specified an app

**Execution result**  
- `success = true`
- file is opened in the selected app

**Failure cases**  
- `target_not_found`: file does not exist
- `target_ambiguous`: multiple file matches
- `permission_denied`: file cannot be opened due to permission
- `app_unavailable`: specified app is not available

**Confirmation rule**  
Never required.

**Notes**  
No edit, move, rename, or delete behavior.

### Action: open_folder

**Purpose**  
Open a local folder in the file manager.

**Allowed targets**  
- `folder`

**Required inputs**  
- `target.type = "folder"`
- resolved `target.path`

**Execution result**  
- `success = true`
- folder is opened or focused in file manager

**Failure cases**  
- `target_not_found`: folder does not exist
- `target_ambiguous`: multiple folder matches
- `permission_denied`: folder cannot be opened
- `unsupported_target_type`: non-`folder` target provided

**Confirmation rule**  
Never required.

**Notes**  
No create, delete, or rename behavior.

### Action: open_website

**Purpose**  
Open a URL in a browser.

**Allowed targets**  
- `browser`

**Required inputs**  
- `target.type = "browser"`
- `parameters.url` with valid `http` or `https` URL

**Execution result**  
- `success = true`
- URL is opened in browser and browser is focused

**Failure cases**  
- `invalid_url`: URL format is invalid
- `target_not_found`: target browser cannot be resolved
- `target_ambiguous`: multiple browser targets
- `permission_denied`: OS denied open request

**Confirmation rule**  
Never required.

**Notes**  
No form submission. No authenticated actions.

### Action: list_windows

**Purpose**  
Return currently visible supported windows.

**Allowed targets**  
- `window`
- `application` (optional app filter)

**Required inputs**  
- no required parameters for global listing
- optional `target` as app filter or `parameters.app_filter`

**Execution result**  
- `success = true`
- `details.windows` list with visible window identifiers and labels

**Failure cases**  
- `permission_denied`: window list access denied
- `unsupported_action`: runtime cannot list windows on current platform adapter
- `target_ambiguous`: filter target resolves to multiple apps/windows

**Confirmation rule**  
Never required.

**Notes**  
No background monitoring. No content inspection.

### Action: focus_window

**Purpose**  
Bring a selected window to the foreground.

**Allowed targets**  
- `window`

**Required inputs**  
- `target.type = "window"`
- window must resolve to one unique window

**Execution result**  
- `success = true`
- selected window is focused

**Failure cases**  
- `target_not_found`: window no longer exists
- `target_ambiguous`: multiple matching windows
- `window_unavailable`: window cannot be focused
- `permission_denied`: OS denied focus request

**Confirmation rule**  
Never required.

**Notes**  
Must fail on ambiguity. Must not auto-select among multiple matches.

### Action: close_window

**Purpose**  
Request close for a selected window.

**Allowed targets**  
- `window`

**Required inputs**  
- `target.type = "window"`
- window resolved to one unique target

**Execution result**  
- `success = true`
- close request completed for selected window

**Failure cases**  
- `confirmation_required`: close is blocked pending explicit confirmation
- `target_not_found`: window no longer exists
- `target_ambiguous`: multiple matching windows
- `window_unavailable`: close request rejected
- `permission_denied`: OS denied close request

**Confirmation rule**  
Sometimes required.

**Notes**  
Must pause for confirmation if unsaved-change risk exists or may exist.

### Action: close_app

**Purpose**  
Request close for an application.

**Allowed targets**  
- `application`

**Required inputs**  
- `target.type = "application"`
- app resolved to one unique target

**Execution result**  
- `success = true`
- close request completed for app

**Failure cases**  
- `confirmation_required`: close blocked pending explicit confirmation
- `app_not_running`: target app is not running
- `target_ambiguous`: multiple app matches
- `permission_denied`: OS denied close request
- `app_unavailable`: app did not respond to close request

**Confirmation rule**  
Sometimes required.

**Notes**  
No force quit in MVP unless explicitly defined and explicitly confirmed. No process-management expansion.

### Action: search_local

**Purpose**  
Search local files or folders by query and optional scope.

**Allowed targets**  
- `folder` (search scope)

**Required inputs**  
- non-empty `parameters.query`
- search scope from `target.path` or explicit `parameters.scope_path`

**Execution result**  
- `success = true`
- `details.matches` list of matching local files/folders

**Failure cases**  
- `missing_parameter`: query is missing
- `target_not_found`: scope path not found
- `permission_denied`: scope is not readable
- `unsupported_target_type`: invalid scope target type

**Confirmation rule**  
Never required.

**Notes**  
Returns matches only. Must not auto-open unless a later explicit open step exists.

### Action: prepare_workspace

**Purpose**  
Run a short, explicit workspace setup sequence.

**Allowed targets**  
- `application`
- `folder`
- `browser`

**Required inputs**  
- `parameters.sequence` as an ordered list composed only of:
  - `open_app`
  - `open_folder`
  - `open_website`
- all sequence targets pre-resolved before execution
- sequence length must stay short and bounded

**Execution result**  
- `success = true`
- all sequence items completed in order
- `details.completed_actions` lists completed sub-actions

**Failure cases**  
- `unsupported_action`: sequence contains disallowed action
- `target_not_found`: any sequence target cannot be resolved
- `target_ambiguous`: any sequence target is ambiguous
- `step_failed`: one sequence item failed; execution stopped at that item
- `permission_denied`: OS denied one sequence item

**Confirmation rule**  
Never required.

**Notes**  
No arbitrary workflows. No background continuation.

### Action: play_music

**Purpose**  
Activate a supported music app and request playback.

**Allowed targets**  
- `application`

**Required inputs**  
- `target.type = "application"`
- supported app target such as `Music` or `Spotify`

**Execution result**  
- `success = true`
- supported app is active
- playback was requested

**Failure cases**  
- `unsupported_target_type`: non-`application` target provided
- `app_unavailable`: music app is not launchable
- `execution_failed`: playback request failed

**Confirmation rule**  
Never required.

**Notes**  
This is a narrow media convenience action for protocol use. It must not expand into arbitrary media control or remote integrations.

## Action Output Shape
```text
ActionResult {
  action: string,
  success: boolean,
  target: Target,
  details?: object,
  error?: {
    code: string,
    message: string
  }
}
```

Result rules:
- On success: `success = true`, `error` omitted.
- On failure: `success = false`, `error` required.
- `action` must equal the executed `Step.action`.
- `target` must be the resolved target used at execution time.
