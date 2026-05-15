# AI Helpdesk Assistant Platform — Project Specification

# Project Goal

Build a generic AI-powered IT Helpdesk Assistant platform with a conversational chat interface.

The platform should support multiple IT support workflows through a modular workflow/plugin architecture.

The frontend must not be designed around a single workflow.

Instead, the application should behave like a centralized AI IT support portal where different workflows can be added over time.

---

# Current Iteration Scope

In this iteration, only one workflow will be fully implemented:

```text
System Slow Diagnostics Workflow
```

Example user query:

```text
My system is slow
```

Future workflows will be added later, including:

```text
Password reset
New employee onboarding
VPN access request
Software installation request
Account unlock
Ticket status lookup
Application outage reporting
Deployment request
Kubernetes issue reporting
```

The architecture must be designed now to support future workflows without major rewrites.

---

# High-Level Product Vision

The system should act as:

```text
AI-powered enterprise IT support assistant
```

The user opens the website and interacts with an AI support chat.

The AI should:

- Understand the user issue
- Detect the correct workflow
- Ask follow-up questions
- Trigger diagnostics or integrations
- Generate ticket drafts
- Create tickets
- Provide status updates

---

# Frontend Vision

The frontend should feel like a modern AI support portal.

It should contain:

- AI chat interface
- Workflow-aware UI cards
- Ticket draft cards
- Diagnostic status cards
- Conversation history
- Multiple workflow entry options

Even though only one workflow is implemented initially, the UI must already support future workflows.

---

# Frontend Requirements

## Main Layout

The frontend should contain:

```text
+--------------------------------------------------+
| Header                                           |
+--------------------------------------------------+
| Sidebar            | Main Chat Area              |
|--------------------|-----------------------------|
| - System Slow      | AI conversation             |
| - Password Reset   | Workflow cards              |
| - VPN Access       | Diagnostic results          |
| - Software Install | Ticket draft cards          |
| - Ticket Status    |                             |
+--------------------------------------------------+
```

Only:

```text
System Slow
```

needs to work in this iteration.

Other menu items can display:

```text
Coming Soon
```

---

# Frontend Technology Stack

Use:

- React
- Vite
- TailwindCSS
- React Query
- Zustand
- Axios

---

# Frontend Components

Create reusable generic components.

## Required Components

```text
components/
  Header.jsx
  Sidebar.jsx
  ChatWindow.jsx
  MessageBubble.jsx
  ChatInput.jsx
  WorkflowCard.jsx
  DiagnosticStatusCard.jsx
  DiagnosticResultCard.jsx
  TicketDraftCard.jsx
  ConfirmationModal.jsx
  LoadingIndicator.jsx
```

These components must be reusable across future workflows.

---

# Frontend Pages

```text
pages/
  HelpdeskHomePage.jsx
  ConversationPage.jsx
  TicketHistoryPage.jsx
  SettingsPage.jsx
```

---

# Frontend Behavior

## Workflow Selection

User can either:

- Type a request in chat
- Select workflow from sidebar

Example:

```text
System Slow Diagnostics
```

When selected:

```text
Assistant:
Please describe the issue you are facing.
```

---

# Backend Requirements

Use:

- Python
- FastAPI
- LangGraph
- LangChain
- Pydantic

---

# Core Backend Architecture

The backend must use a modular workflow registry pattern.

The system should NOT hardcode logic around one workflow.

Use this architecture:

```text
Intent Router
    |
    +--> Workflow Registry
              |
              +--> SystemSlowWorkflow
              +--> NewEmployeeOnboardingWorkflow
              +--> PasswordResetWorkflow
              +--> VpnAccessWorkflow
              +--> TicketStatusWorkflow
```

---

# Workflow Registry

Example:

```python
WORKFLOW_REGISTRY = {
    "system_slow_diagnostics": SystemSlowWorkflow(),
    "password_reset": PasswordResetWorkflow(),
    "vpn_access": VpnAccessWorkflow(),
    "ticket_status": TicketStatusWorkflow()
}
```

Only:

```text
SystemSlowWorkflow
```

should be implemented now.

Other workflows can be placeholder classes.

---

# Current Workflow: System Slow Diagnostics

## Supported User Queries

```text
My system is slow
My laptop is hanging
My computer is freezing
Applications are slow
PC performance is bad
```

---

# System Slow Workflow Goal

The workflow should:

- Collect device identifier
- Detect available diagnostic capability
- Run best-available diagnostics
- Summarize findings
- Generate ticket draft
- Ask user confirmation
- Create mock support ticket

---

# Important Architecture Constraint

The user accesses the system through a browser.

The backend is remote.

Therefore:

```text
The backend cannot directly execute OS commands on the user's machine.
```

The workflow must support multiple enterprise diagnostic methods.

---

# Diagnostic Methods

## Method 1: Intune Integration

If device is Intune-managed:

```text
Backend calls Microsoft Graph Intune APIs
```

Capabilities:

- Device lookup
- Compliance state
- Last sync
- Managed device information
- Approved Intune remediation/script execution

---

## Method 2: SCCM/MECM Integration

If device exists in SCCM:

```text
Backend uses SCCM/MECM APIs or approved scripts
```

Capabilities:

- Hardware inventory
- Software inventory
- Client health
- Approved PowerShell script execution

---

## Method 3: Custom Local Agent

If company has installed local diagnostic agent:

```text
Backend queues diagnostic task
Local agent polls backend
Local agent executes diagnostics
Agent uploads results
```

Capabilities:

- CPU usage
- RAM usage
- Disk usage
- Running processes
- Event logs
- Windows updates

---

## Method 4: Browser Diagnostics Fallback

If no enterprise management exists:

```text
Collect browser-level diagnostics only
Raise support ticket
```

Browser diagnostics can collect:

- Browser version
- OS hint
- CPU core count
- Approximate memory
- Network status
- Page performance metrics

Browser diagnostics cannot collect:

- Process list
- Real CPU usage
- Real RAM usage
- Disk usage
- Event logs

---

# Diagnostic Routing Logic

Priority order:

```text
1. Intune
2. SCCM/MECM
3. Custom Local Agent
4. Browser Diagnostics
```

Example router:

```python
def select_diagnostic_method(device_name):
    if intune_adapter.device_exists(device_name):
        return "intune"

    if sccm_adapter.device_exists(device_name):
        return "sccm"

    if local_agent_adapter.device_registered(device_name):
        return "custom_agent"

    return "browser_only"
```

---

# Workflow Flow

```text
START
  |
  v
intent_classifier
  |
  v
workflow_router
  |
  v
system_slow_workflow
  |
  v
collect_device_name
  |
  v
diagnostic_router
  |
  +--> intune_adapter
  |
  +--> sccm_adapter
  |
  +--> local_agent_adapter
  |
  +--> browser_adapter
  |
  v
normalize_results
  |
  v
generate_summary
  |
  v
generate_ticket_draft
  |
  v
ask_confirmation
  |
  v
create_mock_ticket
  |
  v
END
```

---

# Backend Folder Structure

```text
backend/
  app/
    main.py

    agents/
      intent_router.py
      conversation_agent.py

    workflows/
      system_slow/
        workflow.py
        prompts.py
        state.py

      password_reset/
        workflow.py

      vpn_access/
        workflow.py

      ticket_status/
        workflow.py

    adapters/
      intune/
        adapter.py

      sccm/
        adapter.py

      local_agent/
        adapter.py

      browser/
        adapter.py

      ticketing/
        mock_ticket_adapter.py

    services/
      diagnostic_router.py
      workflow_registry.py
      ticket_service.py

    models/
      request_models.py
      response_models.py
      ticket_models.py
      diagnostic_models.py

    memory/
      session_store.py
      conversation_store.py
```

---

# Frontend Folder Structure

```text
frontend/
  src/
    App.jsx

    pages/
      HelpdeskHomePage.jsx
      ConversationPage.jsx

    components/
      Header.jsx
      Sidebar.jsx
      ChatWindow.jsx
      ChatInput.jsx
      MessageBubble.jsx
      WorkflowCard.jsx
      DiagnosticStatusCard.jsx
      DiagnosticResultCard.jsx
      TicketDraftCard.jsx
      ConfirmationModal.jsx
      LoadingIndicator.jsx

    api/
      agentApi.js
      diagnosticApi.js
      ticketApi.js

    store/
      useConversationStore.js

    utils/
      browserDiagnostics.js
```

---

# API Endpoints

## POST /agent/message

Accepts user message.

Request:

```json
{
  "session_id": "abc123",
  "message": "My system is slow"
}
```

Response:

```json
{
  "type": "assistant_message",
  "message": "Please provide your device name."
}
```

---

## POST /diagnostics/start

Starts diagnostics.

---

## GET /diagnostics/{diagnostic_id}

Returns diagnostic status/result.

---

## POST /diagnostics/browser

Receives browser diagnostics.

---

## POST /tickets/draft

Generates ticket draft.

---

## POST /tickets/create

Creates mock ticket.

---

# Security Requirements

The system must:

- Never execute arbitrary commands from LLM
- Never expose backend secrets to frontend
- Only use approved diagnostic adapters
- Log all diagnostic actions
- Require user confirmation before ticket creation
- Use adapter allowlists
- Prevent prompt injection affecting tool execution

---

# Important LLM Restrictions

The LLM may:

- Detect intent
- Ask follow-up questions
- Summarize results
- Generate ticket descriptions

The LLM must NOT:

- Execute commands
- Generate unrestricted PowerShell
- Override adapter permissions
- Directly access credentials
- Create tickets without confirmation

---

# Iteration 1 Build Scope

Build:

- Generic AI helpdesk frontend
- Sidebar with multiple workflow options
- Chat UI
- Intent router
- Workflow registry
- System slow workflow
- Browser diagnostics
- Mock Intune adapter
- Mock SCCM adapter
- Mock local agent adapter
- Ticket draft generation
- Mock ticket creation

Do not build:

- Real Intune integration
- Real SCCM integration
- Real ServiceNow integration
- Real local endpoint agent

---

# Future Iterations

## Iteration 2

Real Intune integration using Microsoft Graph.

---

## Iteration 3

Real SCCM/MECM integration.

---

## Iteration 4

Real local endpoint agent.

---

## Iteration 5

Real ServiceNow/Jira integration.

---

# Acceptance Criteria

The iteration is complete when:

- Frontend shows multiple workflow options
- Only System Slow workflow is active
- User can type:

  ```text
  My system is slow
  ```

- Assistant asks for device name
- Diagnostic router selects method
- Browser diagnostics work as fallback
- Diagnostic results are summarized
- Ticket draft is generated
- User can confirm ticket creation
- Mock ticket number is returned
- Architecture supports adding future workflows without major rewrites

---

# LLM Integration

The frontend must not call the LLM provider directly.

All LLM calls must go through the backend.

Backend responsibilities:

- Store API keys securely in environment variables
- Call the LLM provider
- Parse structured JSON output
- Route intent to the correct workflow
- Never expose LLM API keys to the browser

Initial LLM tasks:

- Classify user intent
- Extract required fields
- Generate assistant messages
- Summarize diagnostic results
- Generate ticket draft text

The LLM must not:

- Execute tools directly
- Generate unrestricted commands
- Create tickets without backend confirmation logic
