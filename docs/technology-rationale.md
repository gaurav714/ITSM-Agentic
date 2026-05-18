# Technology Rationale

This document explains the main technologies used in the AI Helpdesk Assistant Platform and why they fit this project.

## Project Goal

The application is a modular, conversational IT helpdesk assistant. It routes user requests to workflow-specific handlers, runs approved diagnostics or mock enterprise actions, summarizes results, and helps create support tickets.

The technology choices favor:

- Clear API boundaries between frontend and backend.
- Fast iteration for workflow development.
- Safe use of LLMs with deterministic fallbacks.
- A modular adapter pattern so mock systems can later be replaced with real enterprise integrations.
- A frontend that can render many workflow-specific cards without becoming tightly coupled to each backend workflow.

## Backend

### Python 3

Python is used for the backend because it has strong support for AI/LLM tooling, API development, automation, and system diagnostics.

Why it fits:

- LangChain, LangGraph, and OpenAI SDK integrations are Python-first.
- Backend-local diagnostics can use Python libraries such as `psutil`.
- Mock adapters and workflow logic are quick to build and easy to read.
- Python is a practical language for IT automation and endpoint operations.

### FastAPI

FastAPI provides the REST API layer for chat, workflow discovery, diagnostics, remediation actions, and ticketing.

Why it fits:

- It is lightweight and fast enough for an interactive assistant.
- Pydantic integration gives request and response validation with minimal boilerplate.
- OpenAPI documentation is generated automatically at `/docs`.
- It keeps the backend simple while still supporting future production hardening such as auth, rate limits, and middleware.

Current usage:

- `GET /health`
- `GET /workflows`
- `POST /agent/message`
- `POST /agent/start_workflow`
- `POST /diagnostics/start`
- `POST /diagnostics/browser`
- `POST /diagnostics/action`
- Ticket draft and ticket creation endpoints.

### Uvicorn

Uvicorn runs the FastAPI application during local development.

Why it fits:

- It is the standard ASGI server for FastAPI.
- It supports reload mode for fast backend development.
- It can later sit behind a production web server or container runtime.

### Pydantic and Pydantic Settings

Pydantic models define API payloads and structured internal data. Pydantic Settings handles environment-driven configuration.

Why it fits:

- It validates API contracts at the boundary.
- It makes request and response objects explicit.
- It reduces accidental shape drift between frontend and backend.
- It keeps configuration, such as `OPENAI_API_KEY` and `OPENAI_MODEL`, out of source code.

### LangChain

LangChain is used as the integration layer for LLM calls and structured output helpers.

Why it fits:

- It provides a consistent interface around OpenAI chat models.
- It supports structured output patterns used for extraction and classification.
- It keeps LLM usage isolated behind shared helpers so workflows can fall back deterministically when no API key is configured.

Current usage:

- Intent classification.
- Device-name extraction.
- Confirmation classification.
- Diagnostic summaries.
- Ticket draft generation.

### LangGraph

LangGraph is used for agentic workflow execution where the assistant needs tool-using behavior.

Why it fits:

- Helpdesk workflows are naturally stateful and multi-step.
- Tool execution can be constrained to explicit allowlists.
- It supports future improvements such as checkpointing, tracing, replay, and conditional workflow graphs.
- It separates agent decisions from the actual Python functions that perform approved actions.

Current usage:

- New Employee Onboarding tool-using agent.
- System Slow Diagnostics agent path.
- Windows Update Failure workflow support.

### OpenAI

OpenAI provides the LLM capability when `OPENAI_API_KEY` is configured.

Why it fits:

- Natural-language helpdesk requests need intent routing and flexible extraction.
- The assistant can turn raw diagnostics into clear summaries and ticket drafts.
- The application can still run without OpenAI by using deterministic fallback logic.

Important guardrails:

- The LLM never executes shell commands.
- Tools and adapters are explicitly allowlisted.
- Ticket creation requires confirmation.
- Device names are validated after LLM extraction.
- API keys remain only in the backend environment.

### psutil

`psutil` is used for backend-local diagnostics.

Why it fits:

- It can collect CPU, memory, disk, process, hostname, and OS telemetry from the workstation where the backend runs.
- It avoids relying on a separate local app or MCP server.
- It gives richer diagnostics than browser APIs alone.

Current usage:

- Backend-local diagnostic enrichment for browser fallback cases.
- Allowlisted remediation support, such as closing Microsoft Edge after user approval.

### httpx

`httpx` is included for HTTP client work.

Why it fits:

- Future integrations such as Microsoft Graph, ServiceNow, Jira, or other ITSM APIs will require outbound HTTP calls.
- It supports modern async/sync usage patterns.

### python-dotenv

`python-dotenv` loads local environment variables from `.env` during development.

Why it fits:

- It keeps local secrets and configuration out of source control.
- It makes local setup simple for contributors.

## Frontend

### React

React powers the browser UI.

Why it fits:

- The application is interaction-heavy: chat, workflow cards, diagnostics, ticket drafts, and confirmations.
- Components map cleanly to reusable UI cards.
- It supports a workflow-aware rendering model where the backend sends generic `UICard` payloads and the frontend chooses the right component.

### Vite

Vite is the frontend development and build tool.

Why it fits:

- It starts quickly and supports fast hot reload.
- It keeps the frontend setup small.
- It produces optimized production builds without heavy configuration.

### Tailwind CSS

Tailwind CSS is used for styling.

Why it fits:

- It enables fast UI iteration without creating a large custom CSS layer.
- Utility classes keep component styling close to the component markup.
- It works well for dashboard-style internal tools where consistency and speed matter.

### React Router

React Router handles frontend navigation.

Why it fits:

- The app has multiple views: Home, Conversation, Tickets, and Settings.
- Routes keep the shell simple while allowing workflow-specific conversation pages.

### React Query

React Query manages server data fetching and caching.

Why it fits:

- Workflow lists, ticket lists, and API calls need loading/error states.
- It reduces custom fetch state management.
- It gives a clean foundation for future polling, invalidation, and retries.

### Zustand

Zustand stores lightweight client-side session state.

Why it fits:

- The chat session needs state that survives across component boundaries.
- It is simpler than larger state frameworks for this project.
- It keeps session and UI state explicit without much boilerplate.

### Axios

Axios is used as the frontend HTTP client.

Why it fits:

- It centralizes API calls through a configured client.
- It gives predictable request/response handling.
- It is familiar and easy to extend with auth headers later.

## Architecture Patterns

### Workflow Registry

Every helpdesk flow implements a workflow contract and is registered in the backend workflow registry.

Why it fits:

- New workflows can be added without rewriting the conversation shell.
- The frontend can pull available workflows from `/workflows`.
- It keeps workflow ownership clear.

### Adapter Pattern

Enterprise systems are represented behind adapters, currently mocked for Intune, SCCM, ticketing, and identity.

Why it fits:

- Mock adapters let the project demonstrate end-to-end behavior now.
- Real systems can replace mocks later without changing workflow logic heavily.
- Adapters create an allowlist boundary around external operations.

### Backend-Local Diagnostic Tools

Browser diagnostics are enriched by backend-local Python tools instead of a separate local app or MCP server.

Why it fits:

- It removes an extra deployment component.
- The backend remains the single trusted execution boundary.
- It is easier to audit, validate, and secure than browser-to-localhost calls.

### Generic UI Cards

The backend returns `UICard` objects with a `kind` and `data`. The frontend renders them through card components.

Why it fits:

- Workflows can return specialized visual results without changing the chat protocol.
- The frontend can add new cards incrementally.
- It avoids hardcoding one workflow's shape into the whole UI.

### Deterministic Fallbacks

Every LLM-assisted path has a deterministic fallback.

Why it fits:

- The app remains usable without an OpenAI API key.
- Demos and local development are reliable.
- Critical actions do not depend only on probabilistic model output.

## Current Tradeoffs

- Session state is in memory, which is simple for development but should move to Redis or Postgres for production.
- Enterprise integrations are mocked, which enables fast iteration but does not yet reflect real permissions, latency, or failure modes.
- AuthN/AuthZ is not yet implemented, so the current app assumes trusted local callers.
- The backend-local diagnostic path is useful for development but needs auth, audit logging, and deployment guardrails before production use.
- Tests are currently limited; pytest, frontend tests, and CI should be added as the project hardens.

## Future Technology Direction

Likely next additions:

- Redis or Postgres for persistent sessions and workflow state.
- LangGraph checkpointing for replayable agent state.
- Microsoft Graph integration for real Intune data.
- SCCM/MECM integration through approved enterprise APIs or scripts.
- ServiceNow or Jira integration for real ticketing.
- Authentication and authorization middleware.
- CI/CD with linting, tests, and builds.
- Containerization for backend and frontend deployment.
