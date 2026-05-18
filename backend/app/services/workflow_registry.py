"""Workflow registry — central registration for all supported workflows."""

from typing import Dict

from app.workflows.account_unlock.workflow import AccountUnlockWorkflow
from app.workflows.application_outage.workflow import ApplicationOutageWorkflow
from app.workflows.base import BaseWorkflow
from app.workflows.employee_onboarding.workflow import NewEmployeeOnboardingWorkflow
from app.workflows.password_reset.workflow import PasswordResetWorkflow
from app.workflows.software_install.workflow import SoftwareInstallWorkflow
from app.workflows.system_slow.workflow import SystemSlowWorkflow
from app.workflows.ticket_status.workflow import TicketStatusWorkflow
from app.workflows.vpn_access.workflow import VPNAccessWorkflow
from app.workflows.windows_update_failure.workflow import WindowsUpdateFailureWorkflow

WORKFLOW_REGISTRY: Dict[str, BaseWorkflow] = {
    "system_slow_diagnostics": SystemSlowWorkflow(),
    "new_employee_onboarding": NewEmployeeOnboardingWorkflow(),
    "windows_update_failure": WindowsUpdateFailureWorkflow(),
    "password_reset": PasswordResetWorkflow(),
    "vpn_access": VPNAccessWorkflow(),
    "software_install": SoftwareInstallWorkflow(),
    "account_unlock": AccountUnlockWorkflow(),
    "ticket_status": TicketStatusWorkflow(),
    "application_outage": ApplicationOutageWorkflow(),
}


def get_workflow(workflow_id: str) -> BaseWorkflow | None:
    return WORKFLOW_REGISTRY.get(workflow_id)


def list_workflows() -> list[dict]:
    return [
        {"id": wf_id, "title": wf.title, "active": wf.active}
        for wf_id, wf in WORKFLOW_REGISTRY.items()
    ]
