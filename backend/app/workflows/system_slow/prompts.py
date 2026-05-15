"""Prompt templates used by the System Slow workflow (LLM-optional)."""

SYSTEM_SUMMARY_PROMPT = """You are an IT helpdesk diagnostic assistant.
Summarize the diagnostic data below in 2-3 short sentences for an end user.
Be specific about the bottleneck (CPU, memory, disk, processes) and recommend a next step.
Do not invent metrics that are not present. Plain text only — no markdown.
Device: {device}
Diagnostic method: {method}
Metrics:
{metrics}
"""

DEVICE_EXTRACTION_PROMPT = """Extract the device/computer name from the user's message.
Device names are typically uppercase alphanumeric with hyphens (e.g. LAPTOP-INTUNE-01).
If the user did not provide a device name, return null.
Set confidence between 0 and 1 based on how clearly the device name was stated.

User message: {message}
"""

CONFIRMATION_PROMPT = """The user was asked to confirm creating a support ticket.
Classify their reply as one of: confirm, cancel, unclear.
- confirm: user agrees to create the ticket (e.g. yes, go ahead, file it, do it, sure)
- cancel: user declines (e.g. no, stop, not now, cancel, never mind)
- unclear: anything ambiguous or off-topic

User reply: {message}
"""

TICKET_DRAFT_PROMPT = """You are an IT helpdesk assistant drafting a support ticket for an endpoint performance issue.
Write a concise, professional ticket from the diagnostic data below.

Requirements:
- title: one short line, includes the device name. Max 80 chars.
- description: 3-5 short sentences. Include the diagnostic method, key metrics actually present, and a recommended next step. Plain text only.
- priority: choose Low, Medium, or High based on severity (CPU/memory >= 85% or disk_free < 10 GB => High; mostly normal => Low; otherwise Medium).

Device: {device}
Diagnostic method: {method}
Metrics:
{metrics}
"""

INTENT_CLASSIFY_PROMPT = """Classify the user's IT helpdesk request into one of these workflow ids:
- system_slow_diagnostics
- new_employee_onboarding
- password_reset
- vpn_access
- software_install
- account_unlock
- ticket_status
- application_outage
- unknown

Respond with ONLY the workflow id.
User message: {message}
"""
