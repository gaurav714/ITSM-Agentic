"""Workflow registry — central registration for all supported workflows."""

from typing import Dict

from app.workflows.base import BaseWorkflow, PlaceholderWorkflow
from app.workflows.employee_onboarding.workflow import NewEmployeeOnboardingWorkflow
from app.workflows.system_slow.workflow import SystemSlowWorkflow

WORKFLOW_REGISTRY: Dict[str, BaseWorkflow] = {
    "system_slow_diagnostics": SystemSlowWorkflow(),
    "new_employee_onboarding": NewEmployeeOnboardingWorkflow(),
    "password_reset": PlaceholderWorkflow("password_reset", "Password Reset"),
    "vpn_access": PlaceholderWorkflow("vpn_access", "VPN Access Request"),
    "software_install": PlaceholderWorkflow(
        "software_install", "Software Installation"
    ),
    "account_unlock": PlaceholderWorkflow("account_unlock", "Account Unlock"),
    "ticket_status": PlaceholderWorkflow("ticket_status", "Ticket Status Lookup"),
    "application_outage": PlaceholderWorkflow(
        "application_outage", "Application Outage"
    ),
}


def get_workflow(workflow_id: str) -> BaseWorkflow | None:
    return WORKFLOW_REGISTRY.get(workflow_id)


def list_workflows() -> list[dict]:
    return [
        {"id": wf_id, "title": wf.title, "active": wf.active}
        for wf_id, wf in WORKFLOW_REGISTRY.items()
    ]
