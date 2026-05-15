# Onboarding a User: Flow, API Calls, and LLM Calls

This document explains the current "New Employee Onboarding" flow from the UI request through the backend workflow, OpenAI/LLM calls, LangGraph agent execution, and mock identity tool calls.

## Scope

Workflow id: `new_employee_onboarding`

Primary files:

- `frontend/src/api/agentApi.js`
- `frontend/src/pages/ConversationPage.jsx`
- `backend/app/main.py`
- `backend/app/agents/conversation_agent.py`
- `backend/app/agents/intent_router.py`
- `backend/app/workflows/employee_onboarding/workflow.py`
- `backend/app/workflows/employee_onboarding/agent.py`
- `backend/app/services/llm.py`
- `backend/app/adapters/identity/mock_identity_adapter.py`

## High-Level Flow

```text
User
  -> React chat UI
  -> POST /agent/message or POST /agent/start_workflow
  -> FastAPI app.main
  -> conversation_agent.handle_user_message
  -> intent_router.classify_intent, if needed
  -> NewEmployeeOnboardingWorkflow.handle
  -> LLM structured extraction, if OpenAI is configured
  -> ask for missing details or ask for confirmation
  -> LLM structured confirmation classification, if needed
  -> run_onboarding_agent
  -> LangGraph ReAct agent, if OpenAI is configured
  -> onboarding tools
  -> mock_identity_adapter
  -> backend/data/mock_identity_db.json
  -> AgentMessageResponse with onboarding_progress card
  -> React renders OnboardingProgressCard
```

## Frontend API Calls

The frontend uses Axios from `frontend/src/api/client.js`.

Base URL:

```js
const baseURL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
```

### Start the Workflow

Used when the user selects a workflow route in the UI.

```http
POST /agent/start_workflow
Content-Type: application/json

{
  "session_id": "client-session-id",
  "workflow_id": "new_employee_onboarding"
}
```

Frontend function:

```js
startWorkflow(sessionId, workflowId)
```

Backend handler:

```python
agent_start_workflow(req)
```

What it does:

1. Creates or reuses a `session_id`.
2. Resets the session workflow state.
3. Calls `handle_user_message(session_id, "", forced_workflow=req.workflow_id)`.
4. Returns an `AgentMessageResponse`.

### Send a Chat Message

Used for every user chat turn.

```http
POST /agent/message
Content-Type: application/json

{
  "session_id": "client-session-id",
  "message": "Onboard Jane Doe, jane.doe@example.com, Engineering, Developer"
}
```

Frontend function:

```js
sendAgentMessage(sessionId, message)
```

Backend handler:

```python
agent_message(req)
```

What it does:

1. Validates that `session_id` is present.
2. Calls `handle_user_message(req.session_id, req.message)`.
3. Returns an `AgentMessageResponse`.

### List Workflows

Used by the sidebar/home UI.

```http
GET /workflows
```

Returns the registered workflows, including `new_employee_onboarding`.

## Backend Routing Flow

### 1. FastAPI Entry Point

File: `backend/app/main.py`

For chat messages:

```python
@app.post("/agent/message", response_model=AgentMessageResponse)
def agent_message(req: AgentMessageRequest) -> AgentMessageResponse:
    if not req.session_id:
        raise HTTPException(400, "session_id is required")
    return handle_user_message(req.session_id, req.message)
```

For explicit workflow starts:

```python
@app.post("/agent/start_workflow", response_model=AgentMessageResponse)
def agent_start_workflow(req: StartWorkflowRequest) -> AgentMessageResponse:
    session_id = req.session_id or uuid.uuid4().hex
    session_store.update(session_id, workflow=None, state="idle")
    return handle_user_message(session_id, "", forced_workflow=req.workflow_id)
```

### 2. Conversation Agent / Supervisor

File: `backend/app/agents/conversation_agent.py`

Function:

```python
handle_user_message(session_id, message, forced_workflow=None)
```

Responsibilities:

- Loads session state from `session_store`.
- Appends the user message to session history.
- Chooses the workflow.
- Uses `classify_intent(message)` when no workflow is active.
- Allows switching workflows if the user clearly asks for another workflow.
- Calls the chosen workflow's `handle(session, message)` method.
- Appends the assistant response to history.

For onboarding, it resolves the workflow id:

```text
new_employee_onboarding
```

Then it calls:

```python
NewEmployeeOnboardingWorkflow.handle(session, message)
```

## Onboarding Workflow State Machine

File: `backend/app/workflows/employee_onboarding/workflow.py`

Main method:

```python
NewEmployeeOnboardingWorkflow.handle(session, user_message)
```

Important states:

```text
idle
awaiting_employee_details
awaiting_confirmation
complete
```

### State: idle

When the onboarding workflow starts, it clears previous onboarding state:

```python
self._start_new_request(session)
```

Then it tries to extract employee details from the first message.

If no details are found, it returns:

```text
I can start a new employee onboarding request. Please provide the employee's full name, work email, department, and role.
```

### State: awaiting_employee_details

The workflow calls:

```python
self._handle_employee_details(session, msg)
```

That method:

1. Extracts details from the message.
2. Merges new details into `session["employee"]`.
3. Checks required fields:
   - `full_name`
   - `email`
   - `department`
   - `role`
4. If fields are missing, asks for them.
5. If all fields are present, maps role to access groups.
6. Moves state to `awaiting_confirmation`.
7. Returns an `onboarding_progress` card with pending steps.

### State: awaiting_confirmation

The workflow calls:

```python
self._handle_confirmation(session, msg.lower())
```

If the user cancels, no identity action is taken.

If the user confirms, the workflow calls:

```python
agent_result = run_onboarding_agent(employee, groups)
```

Then it converts the agent tool trace into UI steps and returns the final response.

### State: complete

The workflow reports the completed request and can start another onboarding request if the next message looks like new employee details.

## LLM Calls

All shared LLM helpers live in `backend/app/services/llm.py`.

The configured model comes from:

```python
openai_model: str = "gpt-4o-mini"
```

The OpenAI API key comes from:

```python
OPENAI_API_KEY
```

If no API key is configured, the helper returns `None` and the caller uses deterministic fallback logic.

### Shared LLM Client

```python
def llm_client():
    return _get_llm()
```

Internally, `_get_llm()` creates:

```python
ChatOpenAI(
    model=settings.openai_model,
    api_key=settings.openai_api_key,
    temperature=0,
)
```

### LLM Call 1: Intent Classification

File: `backend/app/agents/intent_router.py`

Function:

```python
classify_intent(message)
```

When used:

- When no workflow is currently active.
- When the conversation agent needs to choose a workflow from a free-text message.

OpenAI call:

```python
llm.invoke([HumanMessage(content=prompt)])
```

Expected result:

```text
new_employee_onboarding
```

Fallback:

- Keyword rules detect phrases like `new employee`, `employee onboarding`, `new hire`, `create AD account`, `work email`, `department`, and `role`.

Note: this file currently creates its own `ChatOpenAI` client instead of using `llm.py`.

### LLM Call 2: Employee Detail Extraction

File: `backend/app/workflows/employee_onboarding/workflow.py`

Function:

```python
_extract_details(msg)
```

OpenAI helper:

```python
llm_structured(
    _DETAIL_EXTRACTION_PROMPT.format(message=msg),
    _EmployeeDetails,
)
```

Prompt purpose:

```text
Extract new employee onboarding details from the user message.
Return null for fields the user did not provide.
Do not invent values.
```

Structured schema:

```python
class _EmployeeDetails(BaseModel):
    full_name: Optional[str]
    email: Optional[str]
    department: Optional[str]
    role: Optional[str]
    manager: Optional[str]
```

Example input:

```text
Please onboard Jane Doe, jane.doe@example.com, Engineering, Developer, manager John Smith.
```

Example structured output:

```json
{
  "full_name": "Jane Doe",
  "email": "jane.doe@example.com",
  "department": "Engineering",
  "role": "Developer",
  "manager": "John Smith"
}
```

Fallback:

- Regex extracts email.
- Label patterns extract fields like `name:`, `department:`, `role:`, `manager:`.
- Comma-separated text can infer name, department, and role.
- Email local-part can infer a name if needed.

### LLM Call 3: Confirmation Classification

File: `backend/app/workflows/employee_onboarding/workflow.py`

Function:

```python
_classify_confirmation(lower)
```

Fast path:

- Deterministic word matching handles obvious replies like `yes`, `confirm`, `go ahead`, `no`, `cancel`.

OpenAI helper:

```python
llm_structured(
    _CONFIRMATION_PROMPT.format(message=lower),
    _Confirmation,
)
```

Structured schema:

```python
class _Confirmation(BaseModel):
    decision: Literal["confirm", "cancel", "unclear"]
```

Used when:

- The user's reply is ambiguous and deterministic matching cannot classify it.

### LLM Call 4: LangGraph ReAct Onboarding Agent

File: `backend/app/workflows/employee_onboarding/agent.py`

Function:

```python
run_onboarding_agent(employee, groups)
```

OpenAI helper:

```python
llm = llm_client()
```

If `llm` exists, the code creates a LangGraph ReAct agent:

```python
agent = create_react_agent(
    llm,
    tools,
    messages_modifier=(
        "You are an enterprise IT onboarding agent. You may only use the provided "
        "tools. Never invent account changes. For a new employee, first call "
        "lookup_identity_user. If the user exists, stop and report duplicate. "
        "If absent, call create_ad_account, assign_role_based_access_groups, "
        "enroll_mfa, and send_welcome_email in a safe order. Return a concise "
        "summary of the performed tool calls."
    ),
)
```

The agent receives this objective:

```json
{
  "employee": {
    "full_name": "Jane Doe",
    "email": "jane.doe@example.com",
    "department": "Engineering",
    "role": "Developer"
  },
  "groups": [
    "EMPLOYEE-BASELINE",
    "M365-STANDARD",
    "MFA-REQUIRED",
    "APP-DEV-USERS",
    "GIT-ACCESS",
    "VPN-ENGINEERING"
  ],
  "required_steps": [
    "lookup_identity_user",
    "create_ad_account only if lookup is absent",
    "assign_role_based_access_groups",
    "enroll_mfa",
    "send_welcome_email"
  ]
}
```

OpenAI/LangGraph call:

```python
result = agent.invoke(
    {
        "messages": [
            HumanMessage(
                content="Execute this approved onboarding request using tools:\n..."
            )
        ]
    }
)
```

The LLM decides which registered tools to call. The tools themselves are Python functions and are explicitly allowlisted.

Fallback:

If no LLM is configured, or the agent errors, the code calls:

```python
_run_deterministic_tool_fallback(employee, groups, trace)
```

That fallback executes the same safe sequence in code.

## Tool Calls Made by the Onboarding Agent

File: `backend/app/workflows/employee_onboarding/agent.py`

The LangGraph agent can only call tools returned by `_build_tools(trace)`.

### Tool: lookup_identity_user

Purpose:

- Checks whether the user already exists.

Implementation:

```python
mock_identity_adapter.get_by_email(email)
```

Trace event:

```json
{
  "tool": "lookup_identity_user",
  "status": "found | not_found",
  "email": "jane.doe@example.com",
  "result": {}
}
```

### Tool: create_ad_account

Purpose:

- Creates a mock AD user account.

Implementation:

```python
mock_identity_adapter.create_user(...)
```

Trace event:

```json
{
  "tool": "create_ad_account",
  "status": "complete",
  "result": {}
}
```

### Tool: assign_role_based_access_groups

Purpose:

- Adds approved RBAC groups to the mock identity user.

Implementation:

```python
mock_identity_adapter.assign_groups(email, groups)
```

### Tool: enroll_mfa

Purpose:

- Marks MFA as enrolled for the mock identity user.

Implementation:

```python
mock_identity_adapter.enroll_mfa(email)
```

### Tool: send_welcome_email

Purpose:

- Marks the welcome email as sent.

Implementation:

```python
mock_identity_adapter.mark_welcome_email_sent(email)
```

## Mock Identity Persistence

File: `backend/app/adapters/identity/mock_identity_adapter.py`

The adapter persists users to:

```text
backend/data/mock_identity_db.json
```

This is the local stand-in for AD or Entra ID. These are not external HTTP calls today.

In a production version, the adapter layer would be the right place to replace local JSON behavior with real API calls such as:

- Microsoft Graph / Entra ID user lookup
- Microsoft Graph / Entra ID user creation
- AD group assignment
- MFA registration policy or invite
- Email provider call
- ServiceNow or Jira ticket creation, if onboarding should create tickets

## Role-to-Group Mapping

File: `backend/app/workflows/employee_onboarding/workflow.py`

Every employee receives baseline groups:

```python
_BASE_GROUPS = ["EMPLOYEE-BASELINE", "M365-STANDARD", "MFA-REQUIRED"]
```

Role keywords add more groups:

```python
"developer" -> ["APP-DEV-USERS", "GIT-ACCESS", "VPN-ENGINEERING"]
"engineer"  -> ["APP-DEV-USERS", "GIT-ACCESS", "VPN-ENGINEERING"]
"hr"        -> ["HRIS-USERS", "EMPLOYEE-DATA-READERS"]
"finance"  -> ["FINANCE-APP-USERS", "EXPENSE-PORTAL-USERS"]
"analyst"  -> ["BI-USERS", "DATA-READERS"]
"manager"  -> ["PEOPLE-MANAGER-TOOLS", "APPROVAL-WORKFLOW-USERS"]
```

## Happy Path Example

### Step 1: User starts onboarding

User message:

```text
Onboard Jane Doe, jane.doe@example.com, Engineering, Developer
```

Frontend sends:

```http
POST /agent/message
```

Backend:

1. `main.agent_message`
2. `conversation_agent.handle_user_message`
3. `intent_router.classify_intent`
4. `NewEmployeeOnboardingWorkflow.handle`
5. `_extract_details`

LLM calls:

- Intent classification may call OpenAI.
- Detail extraction may call OpenAI structured output.

Response:

```json
{
  "type": "assistant_message",
  "message": "I interpreted the employee details and have enough information to onboard them. Reply 'yes' ...",
  "workflow": "new_employee_onboarding",
  "state": "awaiting_confirmation",
  "cards": [
    {
      "kind": "onboarding_progress",
      "data": {
        "employee": {},
        "groups": [],
        "steps": []
      }
    }
  ],
  "requires_input": true
}
```

### Step 2: User confirms

User message:

```text
yes
```

Frontend sends:

```http
POST /agent/message
```

Backend:

1. `NewEmployeeOnboardingWorkflow.handle`
2. `_handle_confirmation`
3. `_classify_confirmation`
4. `run_onboarding_agent(employee, groups)`
5. `create_react_agent(...).invoke(...)`, if OpenAI is configured
6. Tool calls execute against `mock_identity_adapter`

LLM calls:

- Confirmation classification may call OpenAI only if the reply is not obvious.
- LangGraph ReAct agent calls OpenAI to decide and execute tool calls.

Expected tool trace for a new user:

```json
[
  {
    "tool": "lookup_identity_user",
    "status": "not_found"
  },
  {
    "tool": "create_ad_account",
    "status": "complete"
  },
  {
    "tool": "assign_role_based_access_groups",
    "status": "complete"
  },
  {
    "tool": "enroll_mfa",
    "status": "complete"
  },
  {
    "tool": "send_welcome_email",
    "status": "complete"
  }
]
```

Response:

```json
{
  "type": "assistant_message",
  "message": "Onboarding request ONB-XXXXXXXX completed for Jane Doe...",
  "workflow": "new_employee_onboarding",
  "state": "complete",
  "cards": [
    {
      "kind": "onboarding_progress",
      "data": {
        "onboarding_id": "ONB-XXXXXXXX",
        "employee": {},
        "groups": [],
        "account": {},
        "steps": [],
        "agentic": true,
        "agent_summary": "...",
        "tool_trace": []
      }
    }
  ],
  "requires_input": false
}
```

The frontend renders this using:

```text
frontend/src/components/OnboardingProgressCard.jsx
```

## Duplicate User Path

If `lookup_identity_user` returns an existing user:

1. The agent stops.
2. No new account is created.
3. No group, MFA, or welcome-email changes are made.
4. The response tells the user the account already exists.
5. UI steps show create/access/MFA/email as skipped.

This guardrail is implemented both in:

- The LangGraph agent prompt.
- The deterministic fallback path.
- The mock adapter's `create_user`, which returns the existing user if the email already exists.

## Where the System Is Agentic

This flow has three agent-like layers:

1. `conversation_agent.py`
   - Supervises the conversation and routes messages to workflows.

2. `intent_router.py`
   - Uses LLM or keyword fallback to classify the user's intent.

3. `employee_onboarding/agent.py`
   - Uses a LangGraph ReAct agent with OpenAI to decide and execute allowlisted tools.

The most agentic part is the LangGraph ReAct agent in `employee_onboarding/agent.py`.

## What Is Not an External API Yet

These are currently local/mock operations:

- Identity lookup
- AD account creation
- Group assignment
- MFA enrollment
- Welcome email sending

They are tool calls, but not network API calls. The external API currently used by the onboarding flow is OpenAI, when `OPENAI_API_KEY` is set.

## Summary Table

| Stage | Code | API/LLM/Tool |
| --- | --- | --- |
| User sends message | `frontend/src/api/agentApi.js` | HTTP `POST /agent/message` |
| Backend receives message | `backend/app/main.py` | FastAPI endpoint |
| Session and routing | `conversation_agent.py` | Local Python |
| Intent detection | `intent_router.py` | OpenAI LLM or keyword fallback |
| Detail extraction | `workflow.py` | OpenAI structured output or regex fallback |
| Confirmation | `workflow.py` | Deterministic match, then OpenAI structured output if unclear |
| Agent execution | `agent.py` | LangGraph ReAct agent using OpenAI |
| Identity actions | `agent.py` tools | Local tool calls |
| Persistence | `mock_identity_adapter.py` | JSON file-backed mock DB |
| UI result | `OnboardingProgressCard.jsx` | React component |
