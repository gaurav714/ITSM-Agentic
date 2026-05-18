# Workflow Flowcharts

This document shows the runtime flow for key helpdesk workflows. The diagrams use Mermaid syntax, which renders in GitHub and many Markdown viewers.

## Shared Request Flow

All workflows run inside the same FastAPI backend process. A frontend chat turn calls the backend, the conversation agent chooses or continues a workflow, and the selected workflow updates the session state.

```mermaid
flowchart TD
    User[User] --> UI[React chat UI]
    UI --> API[POST /agent/message or /agent/start_workflow]
    API --> FastAPI[FastAPI app.main]
    FastAPI --> Agent[conversation_agent.handle_user_message]
    Agent --> Registry[workflow_registry]
    Registry --> Workflow[Selected workflow.handle]
    Workflow --> Session[Update session state]
    Workflow --> Cards[Return assistant message + UI cards]
    Cards --> UI
```

Important points:

- The backend is one running FastAPI app, not a separate Python script launched for every step.
- Each chat turn is one HTTP request.
- Multi-step workflows continue by storing state in the session store.
- LLM calls are optional; deterministic fallbacks keep the workflow usable without `OPENAI_API_KEY`.

## System Slow Diagnostics

Workflow id: `system_slow_diagnostics`

Primary files:

- `backend/app/workflows/system_slow/workflow.py`
- `backend/app/workflows/system_slow/agent.py`
- `backend/app/services/diagnostic_router.py`
- `backend/app/services/local_diagnostic_tools.py`
- `backend/app/services/ticket_service.py`
- `frontend/src/utils/browserDiagnostics.js`
- `frontend/src/components/DiagnosticResultCard.jsx`

### User-Level Flow

```mermaid
sequenceDiagram
    actor User
    participant UI as React UI
    participant API as FastAPI
    participant WF as SystemSlowWorkflow
    participant Tools as Backend-local diagnostics
    participant Ticket as Ticket service

    User->>UI: "My system is slow"
    UI->>API: POST /agent/message
    API->>WF: Start workflow
    WF-->>UI: Ask triage questions

    User->>UI: Provides context or says still slow
    UI->>API: POST /agent/message
    API->>WF: Classify triage reply
    WF-->>UI: Trigger browser diagnostics

    UI->>UI: Collect browser telemetry
    UI->>API: POST /diagnostics/browser
    UI->>API: POST /agent/message
    API->>WF: Continue awaiting_browser_diagnostics
    WF->>Tools: Run backend-local diagnostics
    Tools-->>WF: CPU, memory, disk, process data, actions
    WF->>Ticket: Prepare ticket draft
    WF-->>UI: Diagnostic result card + optional remediation prompt

    alt Edge remediation available
        User->>UI: Approves or skips closing Edge
        UI->>API: POST /agent/message
        API->>WF: Handle remediation confirmation
        WF-->>UI: Trigger backend action if approved
        UI->>API: POST /diagnostics/action
        API-->>WF: Store action result in session
        WF-->>UI: Offer ticket draft
    end

    User->>UI: Confirms ticket creation
    UI->>API: POST /agent/message
    API->>WF: Create ticket
    WF->>Ticket: create_ticket
    Ticket-->>WF: INC id
    WF-->>UI: Ticket created card
```

### State Flow

```mermaid
flowchart TD
    Start([User starts System Slow workflow])
    Idle[idle]
    Triage[awaiting_triage]
    Browser[awaiting_browser_diagnostics]
    RemediateConfirm[awaiting_remediation_confirmation]
    RemediateAction[awaiting_remediation_action]
    TicketConfirm[awaiting_confirmation]
    Complete[complete]

    Start --> Idle
    Idle --> AskTriage[Ask when it started, one app vs whole system, restart/app cleanup]
    AskTriage --> Triage

    Triage --> Classify{Classify reply}
    Classify -->|partial update| Record[Record known facts and ask if still slow]
    Record --> Triage
    Classify -->|resolved| Complete
    Classify -->|unclear| Clarify[Ask for clearer status/context]
    Clarify --> Triage
    Classify -->|ready to diagnose| Browser

    Browser --> RunDiag[Run diagnostic agent]
    RunDiag --> Router[Diagnostic router: Intune -> SCCM -> browser fallback]
    Router --> BackendLocal[Backend-local psutil tools enrich browser data]
    BackendLocal --> Draft[Generate summary and ticket draft]
    Draft --> EdgeAvailable{Supported remediation available?}

    EdgeAvailable -->|yes| RemediateConfirm
    EdgeAvailable -->|no| TicketConfirm

    RemediateConfirm --> RemDecision{User approves action?}
    RemDecision -->|yes| RemediateAction
    RemDecision -->|no| TicketConfirm
    RemDecision -->|unclear| RemediateConfirm

    RemediateAction --> ActionResult[Receive backend action result]
    ActionResult --> TicketConfirm

    TicketConfirm --> TicketDecision{Create ticket?}
    TicketDecision -->|yes| CreateTicket[Create mock ticket]
    CreateTicket --> Complete
    TicketDecision -->|no| Idle
    TicketDecision -->|unclear| TicketConfirm
```

### What the Workflow Uses

- Triage classification uses a workflow turn agent or deterministic fallback.
- Diagnostics are selected in priority order: Intune, SCCM, then browser fallback with backend-local enrichment.
- Backend-local tools collect workstation telemetry through Python instead of a separate local app.
- Ticket drafts can be LLM-generated, with deterministic fallback text.
- Ticket creation happens only after explicit user confirmation.

## Windows Update Not Working

Workflow id: `windows_update_failure`

Primary files:

- `backend/app/workflows/windows_update_failure/workflow.py`
- `backend/app/services/local_diagnostic_tools.py`
- `frontend/src/pages/ConversationPage.jsx`
- `frontend/src/api/diagnosticApi.js`

### User-Level Flow

```mermaid
sequenceDiagram
    actor User
    participant UI as React UI
    participant API as FastAPI
    participant WF as WindowsUpdateFailureWorkflow
    participant Action as Backend-local action

    User->>UI: "Windows Update is not working"
    UI->>API: POST /agent/message
    API->>WF: Start workflow
    WF-->>UI: Suggest safe user-side checks

    User->>UI: Reports checks or says still failing
    UI->>API: POST /agent/message
    API->>WF: Classify follow-up

    alt User reports partial check
        WF-->>UI: Acknowledge fact and ask if still failing
    else User says fixed
        WF-->>UI: Complete workflow
    else User says still failing
        WF-->>UI: Ask approval for local access
    end

    User->>UI: Approves opening Windows Update settings
    UI->>API: POST /agent/message
    API->>WF: Approval classified
    WF-->>UI: Trigger backend action
    UI->>API: POST /diagnostics/action
    API->>Action: open_windows_update_settings
    Action-->>API: Action result
    API-->>WF: Result available in session
    WF-->>UI: Complete workflow with next instruction
```

### State Flow

```mermaid
flowchart TD
    Start([User starts Windows Update workflow])
    Idle[idle]
    FixResult[awaiting_fix_result]
    AccessApproval[awaiting_access_approval]
    SettingsAction[awaiting_settings_action]
    Complete[complete]

    Start --> Idle
    Idle --> UserFixes[Suggest safe checks: VPN, internet, restart, disk space]
    UserFixes --> FixResult

    FixResult --> Classify{Classify user reply}
    Classify -->|partial update| Summarize[Record known facts]
    Summarize --> AskStill[Ask if Windows Update is still failing]
    AskStill --> FixResult

    Classify -->|resolved| Complete
    Classify -->|unclear| Clarify[Ask whether it works or still fails]
    Clarify --> FixResult

    Classify -->|still failing| RequestAccess[Request approval to open Windows Update settings]
    RequestAccess --> AccessApproval

    AccessApproval --> Approval{User approval?}
    Approval -->|yes| SettingsAction
    Approval -->|no| Complete
    Approval -->|unclear| AccessApproval

    SettingsAction --> Trigger[Trigger backend action: open_windows_update_settings]
    Trigger --> Complete
```

### What the Workflow Uses

- The workflow first recommends safe user-side checks before requesting access.
- Follow-up replies are classified by a workflow turn agent, LLM structured output, or deterministic fallback.
- Local access is gated by explicit user approval.
- The backend action only opens Windows Update settings; it does not run arbitrary commands.
- The workflow completes after the settings action is triggered or if the user says the issue is fixed/declines access.

## Safety Gates Across These Workflows

```mermaid
flowchart LR
    LLM[LLM / agent classification] --> Validate[Validate and normalize decision]
    Validate --> Allowlist[Only allow registered workflow tools/actions]
    Allowlist --> Confirm{User confirmation needed?}
    Confirm -->|yes| Wait[Wait for explicit approval]
    Confirm -->|no| Execute[Execute safe workflow step]
    Wait --> Execute
    Execute --> Persist[Persist next session state]
```

Key guardrails:

- LLMs classify or summarize; they do not directly execute shell commands.
- Workflow actions are allowlisted.
- Remediation and ticket creation require explicit confirmation.
- Session state controls what kind of reply is accepted at each step.
- Backend-local diagnostics/actions are centralized in the backend for easier auditing and future hardening.
