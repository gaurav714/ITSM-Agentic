# Workflow Anatomy

This document explains how workflows are organized in this project, what the
common workflow files do, and how the `system_slow_diagnostics` workflow works
as a complete example.

## What Is a Workflow?

A workflow is a backend conversation flow for a specific IT helpdesk task. It
owns the step-by-step state machine for that task, decides what to ask the user
next, calls agents or tools when needed, and returns structured UI cards to the
frontend.

Workflow folders live under:

```text
backend/app/workflows/
```

Example:

```text
backend/app/workflows/system_slow/
```

## Common Files in a Workflow

A complete workflow can contain these files:

```text
backend/app/workflows/<workflow_name>/
  __init__.py
  workflow.py
  agent.py
  state.py
  prompts.py
```

Not every workflow needs every file. Small or placeholder workflows may only
have `workflow.py`. More agentic workflows usually have all of them.

## File Responsibilities

### `workflow.py`

This is the main workflow controller.

It usually contains:

- The workflow class, such as `SystemSlowWorkflow`.
- The `workflow_id`, title, and active flag.
- The main `handle(session, user_message)` method.
- Conversation states such as `idle`, `awaiting_confirmation`, and `complete`.
- Calls into agents, services, adapters, and ticket creation.
- Response construction using `AgentMessageResponse` and `UICard`.

For System Slow Diagnostics:

```text
backend/app/workflows/system_slow/workflow.py
```

Main class:

```python
class SystemSlowWorkflow(BaseWorkflow):
    workflow_id = "system_slow_diagnostics"
    title = "System Slow Diagnostics"
    active = True
```

Important methods:

- `handle(...)`
- `_start_local_app_diagnostics(...)`
- `_run_diagnostics_and_summarize(...)`
- `_handle_remediation_confirmation(...)`
- `_handle_confirmation(...)`

### `agent.py`

This file contains tool-using or LLM-assisted execution logic.

It is where the workflow delegates work that is more operational than
conversational, such as:

- Selecting tools.
- Running diagnostics.
- Creating a tool trace.
- Preparing a ticket draft.
- Using a LangGraph ReAct agent when an LLM is configured.
- Falling back to deterministic logic when no LLM is configured.

For System Slow Diagnostics:

```text
backend/app/workflows/system_slow/agent.py
```

Main function:

```python
run_system_slow_agent(device_name, session_id, diagnostic_id)
```

Tools exposed to the agent:

- `select_diagnostic_method`
- `run_system_diagnostics`
- `prepare_ticket_draft`

The agent can only use these allowlisted tools.

### `state.py`

This file defines the workflow state schema.

For LangGraph-based workflows, this is commonly a `TypedDict` describing fields
that may exist while the graph executes.

For System Slow Diagnostics:

```text
backend/app/workflows/system_slow/state.py
```

Schema:

```python
class SystemSlowState(TypedDict, total=False):
    session_id: str
    user_message: str
    device_name: Optional[str]
    diagnostic_id: Optional[str]
    diagnostic: Optional[Dict[str, Any]]
    summary: Optional[str]
    next_state: str
    assistant_message: str
```

This is separate from the persisted chat session dictionary. The session stores
conversation progress, while the LangGraph state schema describes graph data.

### `prompts.py`

This file holds prompt templates used by the workflow or its agent.

Keeping prompts in one file makes the workflow easier to maintain and avoids
burying large prompt strings inside business logic.

For System Slow Diagnostics:

```text
backend/app/workflows/system_slow/prompts.py
```

Important prompts:

- `SYSTEM_SUMMARY_PROMPT`
- `DEVICE_EXTRACTION_PROMPT`
- `CONFIRMATION_PROMPT`
- `TICKET_DRAFT_PROMPT`
- `INTENT_CLASSIFY_PROMPT`

The workflow uses deterministic fallbacks when LLM calls are unavailable.

### `__init__.py`

This file marks the folder as a Python package.

It may be empty. Its main purpose is to allow imports such as:

```python
from app.workflows.system_slow.workflow import SystemSlowWorkflow
```

## Shared Workflow Contract

All real workflows inherit from:

```text
backend/app/workflows/base.py
```

The base class requires every workflow to implement:

```python
def handle(
    self,
    session: Dict[str, Any],
    user_message: str,
) -> AgentMessageResponse:
    ...
```

This keeps every workflow compatible with the central conversation agent.

## Workflow Registration

Workflows are registered in:

```text
backend/app/services/workflow_registry.py
```

System Slow Diagnostics is registered as:

```python
WORKFLOW_REGISTRY = {
    "system_slow_diagnostics": SystemSlowWorkflow(),
    ...
}
```

The registry lets the backend:

- Find a workflow by id.
- List available workflows for the frontend.
- Distinguish active workflows from placeholders.

## System Slow Diagnostics Example

Workflow id:

```text
system_slow_diagnostics
```

Primary files:

- `backend/app/workflows/system_slow/workflow.py`
- `backend/app/workflows/system_slow/agent.py`
- `backend/app/workflows/system_slow/state.py`
- `backend/app/workflows/system_slow/prompts.py`
- `backend/app/services/diagnostic_router.py`
- `backend/app/services/ticket_service.py`
- `backend/app/services/workflow_registry.py`

## High-Level Flow

```text
User
  -> React chat UI
  -> POST /agent/message
  -> FastAPI backend
  -> conversation_agent.handle_user_message
  -> intent_router.classify_intent, if needed
  -> SystemSlowWorkflow.handle
  -> request browser/local app diagnostics
  -> browser posts diagnostic result
  -> run_system_slow_agent
  -> diagnostic tools
  -> summary and ticket draft
  -> optional remediation action
  -> optional ticket creation
  -> AgentMessageResponse with UI cards
```

## System Slow State Machine

The workflow stores progress in the session dictionary.

Important states:

```text
idle
awaiting_browser_diagnostics
awaiting_remediation_confirmation
awaiting_remediation_action
awaiting_confirmation
complete
```

### `idle`

The workflow starts. It creates a diagnostic id, stores a device name placeholder
if needed, and asks the frontend to trigger browser/local app diagnostics.

Response metadata includes:

```json
{
  "trigger_browser_diagnostics": true
}
```

### `awaiting_browser_diagnostics`

The browser has been asked to collect diagnostics. Once diagnostic data is
available, the workflow calls:

```python
run_system_slow_agent(...)
```

The result includes:

- Normalized diagnostic data.
- A summary.
- A ticket draft.
- A tool trace.
- Whether the LLM agent was used.

### `awaiting_remediation_confirmation`

If diagnostics show that a supported local action is available, such as closing
Microsoft Edge, the workflow asks the user for permission.

If the user confirms, the backend returns metadata asking the frontend/local app
to run the action.

### `awaiting_remediation_action`

The workflow waits for the local action result. After receiving it, the workflow
offers to create a support ticket if the issue persists.

### `awaiting_confirmation`

The workflow asks whether to create the prepared support ticket.

If the user confirms:

```python
create_ticket(draft)
```

If the user cancels, the workflow returns to `idle`.

### `complete`

The support ticket has been created and the ticket id is stored in the session.

## Agent Execution

The System Slow agent lives in:

```text
backend/app/workflows/system_slow/agent.py
```

The main entry point is:

```python
run_system_slow_agent(device_name, session_id, diagnostic_id)
```

When an LLM is configured, the code creates a LangGraph ReAct agent with these
tools:

```text
select_diagnostic_method
run_system_diagnostics
prepare_ticket_draft
```

The agent receives an objective like:

```json
{
  "device_name": "LOCAL-ENDPOINT",
  "session_id": "session-id",
  "diagnostic_id": "DIAG-1234ABCD",
  "required_steps": [
    "select_diagnostic_method",
    "run_system_diagnostics",
    "prepare_ticket_draft"
  ]
}
```

If no LLM is configured, or if the agent fails, the workflow uses:

```python
_run_deterministic_tool_fallback(...)
```

That fallback runs the same core steps in a fixed order.

## Prompt Usage

System Slow Diagnostics uses prompts for optional LLM behavior:

| Prompt | Purpose |
| --- | --- |
| `SYSTEM_SUMMARY_PROMPT` | Summarize diagnostic data for the user. |
| `CONFIRMATION_PROMPT` | Classify ambiguous yes/no replies. |
| `TICKET_DRAFT_PROMPT` | Draft a support ticket from diagnostics. |
| `DEVICE_EXTRACTION_PROMPT` | Extract a device name from user text. |
| `INTENT_CLASSIFY_PROMPT` | Classify user requests into workflow ids. |

The workflow does not depend entirely on the LLM. Common yes/no replies,
diagnostic execution, and ticket drafting all have deterministic fallback paths.

## UI Cards Returned by the Workflow

System Slow Diagnostics can return cards such as:

- `diagnostic_status`
- `diagnostic_result`
- `ticket_draft`
- `ticket_created`

These cards let the frontend render structured workflow results instead of only
plain chat text.

Example diagnostic status card:

```json
{
  "kind": "diagnostic_status",
  "data": {
    "diagnostic_id": "DIAG-1234ABCD",
    "method": "local_app",
    "status": "collecting_local_app_metrics",
    "device_name": "LOCAL-ENDPOINT"
  }
}
```

## Template for Creating a New Workflow

Use this structure for a new full workflow:

```text
backend/app/workflows/my_new_workflow/
  __init__.py
  workflow.py
  agent.py
  state.py
  prompts.py
```

Minimum implementation:

1. Create a workflow class in `workflow.py`.
2. Inherit from `BaseWorkflow`.
3. Set `workflow_id`, `title`, and `active`.
4. Implement `handle(session, user_message)`.
5. Register the workflow in `workflow_registry.py`.
6. Add prompts, state, and an agent only if the workflow needs them.

Example skeleton:

```python
from typing import Any, Dict

from app.models.schemas import AgentMessageResponse
from app.workflows.base import BaseWorkflow


class MyNewWorkflow(BaseWorkflow):
    workflow_id = "my_new_workflow"
    title = "My New Workflow"
    active = True

    def handle(
        self,
        session: Dict[str, Any],
        user_message: str,
    ) -> AgentMessageResponse:
        session["workflow"] = self.workflow_id
        session["state"] = "complete"

        return AgentMessageResponse(
            message="Workflow completed.",
            workflow=self.workflow_id,
            state="complete",
            requires_input=False,
        )
```

Registry entry:

```python
from app.workflows.my_new_workflow.workflow import MyNewWorkflow

WORKFLOW_REGISTRY = {
    "my_new_workflow": MyNewWorkflow(),
    ...
}
```

## Summary

In this project:

- `workflow.py` owns the conversation state machine.
- `agent.py` owns tool execution and agentic behavior.
- `state.py` defines graph state shape.
- `prompts.py` stores LLM prompt templates.
- `workflow_registry.py` makes the workflow discoverable.
- `BaseWorkflow` defines the common contract every workflow must follow.

The `system_slow_diagnostics` workflow is the best complete example because it
uses all of these pieces: session state, LangGraph wiring, tool execution,
LLM-optional prompts, local diagnostics, remediation, ticket drafting, and final
ticket creation.

## Windows Update Failure Example

Workflow id:

```text
windows_update_failure
```

Primary files:

- `backend/app/workflows/windows_update_failure/workflow.py`
- `backend/app/workflows/windows_update_failure/agent.py`
- `local_app/app/tools.py`
- `local_app/app/local_app.py`

This workflow is intentionally agentic. The LangGraph flow enters one decision
node, `agent_interpret_and_decide`, on every user turn. That node calls the LLM
ReAct decision agent, which must choose exactly one workflow action:

- `ask_check`
- `request_access`
- `run_tool`
- `mark_resolved`
- `stop_workflow`
- `clarify`

The workflow then routes to a user-facing node such as `prompt_user_check`,
`request_local_access`, `trigger_local_tool`, or `finish_or_clarify`.

### Windows Update Session Context

The workflow persists its memory in the shared session dictionary:

```text
windows_update_checks_discussed
windows_update_agent_trace
windows_update_last_decision
windows_update_access_approved
windows_update_tool_results
windows_update_current_check
windows_update_llm_called
windows_update_agent_error
```

The model receives raw user text plus workflow context, including checks already
discussed, the current prompted check, local-access approval state, previous
local tool results, available checks, and allowlisted local tools.

### Local Access Approval Rule

The `awaiting_access_approval` state is treated as the approval-answer turn.
When the workflow is in that state:

- A clear approval should make the model choose `run_tool`.
- A denial or cancellation should make the model choose `stop_workflow`.
- An ambiguous reply should make the model choose `clarify`.
- The model should not choose `request_access` again.

The workflow still enforces deterministic safety gates. If the model tries to
run a tool before access is approved, the workflow converts that into
`request_access`. If the model repeats `request_access` while already waiting
for approval, the workflow blocks the loop and asks for a concise clarification
instead.

### Windows Update Local Tools

Allowed local app actions for this workflow:

```text
collect_windows_update_status
open_windows_update_settings
```

The first recommended tool after approval is
`collect_windows_update_status`. `open_windows_update_settings` can be selected
later by the agent based on the conversation and prior tool results.
