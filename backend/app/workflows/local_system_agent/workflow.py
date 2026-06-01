"""General local system agent workflow.

The backend plans a PowerShell task, the browser asks the localhost app to run
it after user confirmation, and this workflow summarizes the returned result.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, Literal

from pydantic import BaseModel, Field

from app.models.schemas import AgentMessageResponse, UICard
from app.services.llm import llm_structured
from app.workflows.base import BaseWorkflow


class _LocalTaskPlan(BaseModel):
    summary: str = Field(description="Short user-facing summary of the local task.")
    risk_level: Literal["low", "medium", "high"] = "medium"
    command: str = Field(description="PowerShell command to execute as current user.")
    timeout_seconds: int = 15
    expected_result: str = ""


class LocalSystemAgentWorkflow(BaseWorkflow):
    workflow_id = "local_system_agent"
    title = "Local System Agent"
    active = True

    def handle(
        self, session: Dict[str, Any], user_message: str
    ) -> AgentMessageResponse:
        if session.get("workflow") != self.workflow_id:
            self._start_session(session)

        local_action_result = session.pop("local_action_result", None)
        if local_action_result:
            return self._handle_local_result(session, local_action_result)

        message = (user_message or "").strip()
        if not message or _is_activation_phrase(message):
            session["state"] = "awaiting_request"
            return AgentMessageResponse(
                message=(
                    "Local System Agent is active. Ask me a workstation question, "
                    "for example: how much disk space is free on C drive?"
                ),
                workflow=self.workflow_id,
                state="awaiting_request",
            )

        plan = _plan_local_task(message)
        if plan is None:
            session["state"] = "awaiting_request"
            return AgentMessageResponse(
                message=(
                    "I need the backend LLM configured before I can safely plan "
                    "general local system commands. Set OPENAI_API_KEY and try again."
                ),
                workflow=self.workflow_id,
                state="awaiting_request",
                cards=[
                    UICard(
                        kind="workflow",
                        data={
                            "title": self.title,
                            "step": "planner_unavailable",
                            "agentic": False,
                        },
                    )
                ],
            )

        task_id = f"LOCAL-{uuid.uuid4().hex[:8].upper()}"
        task = {
            "action": "run_powershell_task",
            "task_id": task_id,
            "summary": plan.summary,
            "risk_level": plan.risk_level,
            "command": plan.command,
            "timeout_seconds": _clamp_timeout(plan.timeout_seconds),
            "expected_result": plan.expected_result,
            "requires_confirmation": True,
        }
        session["state"] = "awaiting_tool_result"
        session["local_system_pending_task"] = task

        return AgentMessageResponse(
            message=(
                f"I can run a local PowerShell task: {plan.summary}\n\n"
                "Please review and approve the command in the confirmation prompt."
            ),
            workflow=self.workflow_id,
            state="awaiting_tool_result",
            metadata={"trigger_local_app_action": task},
            cards=[
                UICard(
                    kind="workflow",
                    data={
                        "title": self.title,
                        "step": "planned_local_task",
                        "task_id": task_id,
                        "summary": plan.summary,
                        "risk_level": plan.risk_level,
                        "command": plan.command,
                        "expected_result": plan.expected_result,
                    },
                )
            ],
            requires_input=False,
        )

    def _start_session(self, session: Dict[str, Any]) -> None:
        session["workflow"] = self.workflow_id
        session["state"] = "awaiting_request"
        session.pop("local_system_pending_task", None)
        session.pop("local_action_result", None)

    def _handle_local_result(
        self, session: Dict[str, Any], result: Dict[str, Any]
    ) -> AgentMessageResponse:
        pending = session.pop("local_system_pending_task", {}) or {}
        session["state"] = "awaiting_request"
        summary = _summarize_local_result(pending, result)
        status = result.get("status") or "unknown"

        return AgentMessageResponse(
            message=summary,
            workflow=self.workflow_id,
            state="awaiting_request",
            cards=[
                UICard(
                    kind="workflow",
                    data={
                        "title": self.title,
                        "step": "local_task_result",
                        "task_id": result.get("task_id") or pending.get("task_id"),
                        "status": status,
                        "summary": pending.get("summary", ""),
                        "stdout": _truncate(str(result.get("stdout") or ""), 1200),
                        "stderr": _truncate(str(result.get("stderr") or ""), 1200),
                        "exit_code": result.get("exit_code"),
                        "needs_elevation": bool(result.get("needs_elevation")),
                    },
                )
            ],
        )


def _plan_local_task(user_request: str) -> _LocalTaskPlan | None:
    deterministic = _deterministic_plan(user_request)
    if deterministic is not None:
        return deterministic

    prompt = f"""
You are planning a single current-user PowerShell task for a localhost helper app.

Rules:
- Return exactly one PowerShell command.
- The command must run as the current user. Do not attempt elevation, UAC,
  credential prompts, remoting, downloads, installs, or destructive deletion.
- Prefer read-only commands for information requests.
- Use bounded, non-interactive commands.
- If admin rights may be needed, still produce the best current-user command;
  the local app will report needs_elevation on access denied.
- Do not wrap the command in powershell.exe; only provide the command body.

User request:
{user_request}
"""
    plan = llm_structured(prompt, _LocalTaskPlan)
    if plan is None:
        return None
    command = _clean_command(plan.command)
    if not command:
        return None
    plan.command = command
    plan.timeout_seconds = _clamp_timeout(plan.timeout_seconds)
    if not plan.summary:
        plan.summary = "Run a local PowerShell task for this request."
    return plan


def _deterministic_plan(user_request: str) -> _LocalTaskPlan | None:
    text = (user_request or "").lower()
    if re.search(r"\b(disk\s+(space|usage|free)|free\s+space|c\s*drive)\b", text):
        drive = "C"
        match = re.search(r"\b([a-z])\s*[: ]?\s*drive\b", text)
        if match:
            drive = match.group(1).upper()
        return _LocalTaskPlan(
            summary=f"Check free and used disk space on {drive}: drive.",
            risk_level="low",
            command=(
                f"Get-PSDrive -Name {drive} | "
                "Select-Object Name,Used,Free,"
                "@{Name='UsedGB';Expression={[math]::Round($_.Used/1GB,2)}},"
                "@{Name='FreeGB';Expression={[math]::Round($_.Free/1GB,2)}} | "
                "ConvertTo-Json"
            ),
            timeout_seconds=10,
            expected_result="JSON with used and free disk space in bytes and GB.",
        )

    if re.search(r"\b(windows\s+version|os\s+version|operating\s+system)\b", text):
        return _LocalTaskPlan(
            summary="Check the Windows version and build.",
            risk_level="low",
            command=(
                "Get-ComputerInfo | "
                "Select-Object WindowsProductName,WindowsVersion,OsBuildNumber,"
                "OsArchitecture | ConvertTo-Json"
            ),
            timeout_seconds=15,
            expected_result="JSON with Windows product, version, build, and architecture.",
        )

    if re.search(r"\b(top\s+process(es)?|running\s+process(es)?|process\s+usage)\b", text):
        return _LocalTaskPlan(
            summary="List the top running processes by memory usage.",
            risk_level="low",
            command=(
                "Get-Process | Sort-Object WorkingSet -Descending | Select-Object -First 10 "
                "ProcessName,Id,@{Name='MemoryMB';Expression={[math]::Round($_.WorkingSet/1MB,1)}} | "
                "ConvertTo-Json"
            ),
            timeout_seconds=10,
            expected_result="JSON list of the top processes by memory usage.",
        )

    if re.search(r"\b(memory\s+usage|ram\s+usage)\b", text):
        return _LocalTaskPlan(
            summary="Check current physical memory usage.",
            risk_level="low",
            command=(
                "$os = Get-CimInstance Win32_OperatingSystem; "
                "[pscustomobject]@{"
                "TotalGB=[math]::Round($os.TotalVisibleMemorySize/1MB,2);"
                "FreeGB=[math]::Round($os.FreePhysicalMemory/1MB,2);"
                "UsedGB=[math]::Round(($os.TotalVisibleMemorySize-$os.FreePhysicalMemory)/1MB,2);"
                "UsedPct=[math]::Round((($os.TotalVisibleMemorySize-$os.FreePhysicalMemory)/$os.TotalVisibleMemorySize)*100,1)"
                "} | ConvertTo-Json"
            ),
            timeout_seconds=10,
            expected_result="JSON with total, free, used, and percent memory usage.",
        )

    if re.search(r"\b(cpu\s+usage|processor\s+usage)\b", text):
        return _LocalTaskPlan(
            summary="Check current CPU usage.",
            risk_level="low",
            command=(
                "Get-CimInstance Win32_Processor | "
                "Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,LoadPercentage | "
                "ConvertTo-Json"
            ),
            timeout_seconds=10,
            expected_result="JSON with CPU model, core counts, and load percentage.",
        )

    return None


def _summarize_local_result(pending: Dict[str, Any], result: Dict[str, Any]) -> str:
    status = result.get("status") or "unknown"
    needs_elevation = bool(result.get("needs_elevation"))
    stdout = _truncate(str(result.get("stdout") or ""), 2500)
    stderr = _truncate(str(result.get("stderr") or ""), 1000)
    message = result.get("message") or "The local task returned a result."

    if needs_elevation:
        return (
            f"{message} This appears to require administrator privileges. "
            "I did not attempt elevation because the local app runs as the current user."
        )

    if status == "complete":
        body = stdout or message
        task = pending.get("summary") or "Local task"
        return f"{task}\n\nResult:\n{body}".strip()
    if status == "timeout":
        return message or "The local task timed out before it finished."
    details = stderr or stdout or message
    return f"Local task status: {status}. {details}".strip()


def _clean_command(command: str) -> str:
    command = (command or "").strip()
    command = re.sub(r"^```(?:powershell|ps1|pwsh)?", "", command, flags=re.I).strip()
    command = re.sub(r"```$", "", command).strip()
    return command


def _is_activation_phrase(message: str) -> bool:
    return bool(
        re.fullmatch(
            r"\s*(local\s+system\s+agent|local\s+agent|system\s+agent)\s*",
            message or "",
            flags=re.I,
        )
    )


def _clamp_timeout(value: int) -> int:
    try:
        timeout = int(value)
    except Exception:
        timeout = 15
    return max(3, min(timeout, 60))


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...[truncated]"
