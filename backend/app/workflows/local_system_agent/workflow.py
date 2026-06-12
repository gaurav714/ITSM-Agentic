"""General local system agent workflow.

The backend plans a bounded PowerShell task, the browser asks the localhost app
to run it after user confirmation, and this workflow interprets the returned
result for the user.
"""

from __future__ import annotations

import json
import re
import subprocess
import uuid
from typing import Any, Dict, Literal

from pydantic import BaseModel, Field

from app.models.schemas import AgentMessageResponse, UICard
from app.services.llm import llm_structured
from app.workflows.base import BaseWorkflow

MAX_COMMAND_LENGTH = 2500
MAX_EVIDENCE_CATEGORIES = 5
MAX_CHAT_EXCERPT = 700
MAX_JSON_LIST_ITEMS = 5
PLANNER_METADATA_KEYS = {
    "goal",
    "ev",
    "sc",
    "lim",
    "schema",
    "diagnostic_goal",
    "evidence_to_collect",
    "success_criteria",
    "limitations",
    "expected_result",
    "output_schema_hint",
}
RESULT_ORIENTED_KEYS = {
    "installed",
    "found",
    "exists",
    "present",
    "available",
    "detected",
    "hits",
    "paths",
    "path",
    "checked",
    "status",
    "version",
    "errors",
    "error",
    "inconclusive",
    "manifest",
    "manifests",
    "location",
    "locations",
    "devices",
    "device",
    "name",
    "ok",
    "time",
    "local",
    "date",
    "timezone",
    "tz",
    "offset",
    "utc_offset",
    "hostname",
    "computername",
    "computer_name",
    "machine",
    "user",
    "username",
    "domain",
}


class _LocalTaskPlan(BaseModel):
    summary: str = Field(description="Short user-facing summary of the local task.")
    risk_level: Literal["low", "medium", "high"] = "medium"
    command: str = Field(description="PowerShell command to execute as current user.")
    timeout_seconds: int = 15
    diagnostic_goal: str = ""
    evidence_to_collect: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    output_schema_hint: str = ""
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
        if _is_protocol_message(message):
            session["state"] = "awaiting_request"
            return AgentMessageResponse(
                message=(
                    "Local System Agent is active. Ask me what you want checked "
                    "or done on this workstation."
                ),
                workflow=self.workflow_id,
                state="awaiting_request",
            )

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
                    "I could not generate a compact, useful local diagnostic command "
                    "for that request. Try narrowing the request, or check that the "
                    "backend LLM is configured correctly."
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
            "user_request": message,
            "summary": plan.summary,
            "risk_level": plan.risk_level,
            "command": plan.command,
            "timeout_seconds": _clamp_timeout(plan.timeout_seconds),
            "diagnostic_goal": plan.diagnostic_goal,
            "evidence_to_collect": plan.evidence_to_collect,
            "success_criteria": plan.success_criteria,
            "limitations": plan.limitations,
            "output_schema_hint": plan.output_schema_hint,
            "expected_result": plan.expected_result,
            "interpretation_hint": _interpretation_hint_for_plan(plan),
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
                        "command_preview": _truncate(plan.command, 500),
                        "diagnostic_goal": plan.diagnostic_goal,
                        "evidence_to_collect": plan.evidence_to_collect,
                        "success_criteria": plan.success_criteria,
                        "limitations": plan.limitations,
                        "output_schema_hint": plan.output_schema_hint,
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
        returned_context = result.get("task_context") or {}
        session_context = session.pop("local_system_pending_task", {}) or {}
        pending = {**returned_context, **session_context}
        repair = _maybe_repair_failed_plan(pending, result)
        if repair is not None:
            session["state"] = "awaiting_tool_result"
            session["local_system_pending_task"] = repair
            return AgentMessageResponse(
                message=(
                    "The previous generated PowerShell had a syntax problem, so I prepared "
                    "a safer revised local task.\n\nPlease review and approve the new command."
                ),
                workflow=self.workflow_id,
                state="awaiting_tool_result",
                metadata={"trigger_local_app_action": repair},
                cards=[
                    UICard(
                        kind="workflow",
                        data={
                            "title": self.title,
                            "step": "replanned_local_task",
                            "task_id": repair.get("task_id"),
                            "summary": repair.get("summary"),
                            "risk_level": repair.get("risk_level"),
                            "command_preview": _truncate(str(repair.get("command") or ""), 500),
                            "diagnostic_goal": repair.get("diagnostic_goal", ""),
                            "evidence_to_collect": repair.get("evidence_to_collect", []),
                            "success_criteria": repair.get("success_criteria", []),
                            "limitations": repair.get("limitations", []),
                            "output_schema_hint": repair.get("output_schema_hint", ""),
                            "expected_result": repair.get("expected_result", ""),
                        },
                    )
                ],
                requires_input=False,
            )
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
                        "user_request": pending.get("user_request", ""),
                        "command_preview": _truncate(str(pending.get("command") or ""), 500),
                        "diagnostic_goal": pending.get("diagnostic_goal", ""),
                        "evidence_to_collect": pending.get("evidence_to_collect", []),
                        "success_criteria": pending.get("success_criteria", []),
                        "limitations": pending.get("limitations", []),
                        "output_schema_hint": pending.get("output_schema_hint", ""),
                        "expected_result": pending.get("expected_result", ""),
                        "interpretation_hint": pending.get("interpretation_hint", ""),
                        "stdout": _truncate(str(result.get("stdout") or ""), 1200),
                        "stderr": _truncate(str(result.get("stderr") or ""), 1200),
                        "exit_code": result.get("exit_code"),
                        "needs_elevation": bool(result.get("needs_elevation")),
                    },
                )
            ],
        )


def _plan_local_task(
    user_request: str, validation_errors: list[str] | None = None
) -> _LocalTaskPlan | None:
    deterministic = _deterministic_plan(user_request)
    if deterministic is not None and not validation_errors:
        return deterministic

    plan = _prepare_plan(
        _safe_request_llm_plan(user_request, validation_errors=validation_errors)
    )
    errors = _validate_plan(plan, user_request)
    if plan is not None and not errors:
        return plan

    revised = _prepare_plan(_safe_request_llm_plan(user_request, validation_errors=errors))
    if revised is not None and not _validate_plan(revised, user_request):
        return revised
    return _fallback_generic_plan(user_request)


def _safe_request_llm_plan(
    user_request: str, validation_errors: list[str] | None = None
) -> _LocalTaskPlan | None:
    try:
        return _request_llm_plan(user_request, validation_errors=validation_errors)
    except Exception:
        return None


def _task_from_plan(user_request: str, plan: _LocalTaskPlan, repair_count: int = 0) -> Dict[str, Any]:
    task_id = f"LOCAL-{uuid.uuid4().hex[:8].upper()}"
    return {
        "action": "run_powershell_task",
        "task_id": task_id,
        "user_request": user_request,
        "summary": plan.summary,
        "risk_level": plan.risk_level,
        "command": plan.command,
        "timeout_seconds": _clamp_timeout(plan.timeout_seconds),
        "diagnostic_goal": plan.diagnostic_goal,
        "evidence_to_collect": plan.evidence_to_collect,
        "success_criteria": plan.success_criteria,
        "limitations": plan.limitations,
        "output_schema_hint": plan.output_schema_hint,
        "expected_result": plan.expected_result,
        "interpretation_hint": _interpretation_hint_for_plan(plan),
        "requires_confirmation": True,
        "repair_count": repair_count,
    }


def _maybe_repair_failed_plan(pending: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any] | None:
    if (result.get("status") or "").lower() not in {"failed", "rejected"}:
        return None
    if int(pending.get("repair_count") or 0) >= 1:
        return None

    error_text = _clean_powershell_error(
        "\n".join(
            str(value or "")
            for value in (
                result.get("stderr"),
                result.get("stdout"),
                result.get("message"),
                " ".join(str(item) for item in result.get("errors") or []),
            )
        )
    )
    if not _looks_like_powershell_syntax_failure(error_text):
        return None

    user_request = str(pending.get("user_request") or "").strip()
    if not user_request:
        return None

    plan = _plan_local_task(
        user_request,
        validation_errors=[
            "The previous generated PowerShell failed at runtime with a parser/syntax error.",
            _truncate(error_text, 300),
            "Produce a simpler command. Avoid complex quoting, nested regex literals, hashtable syntax that is easy to break, and environment variable syntax without braces for names with parentheses.",
        ],
    )
    if plan is None:
        return None
    return _task_from_plan(user_request, plan, repair_count=1)


def _request_llm_plan(
    user_request: str, validation_errors: list[str] | None = None
) -> _LocalTaskPlan | None:
    retry = ""
    if validation_errors:
        retry = (
            "\nThe previous plan was rejected for these reasons:\n- "
            + "\n- ".join(validation_errors)
            + "\nRevise the plan so it satisfies every rule.\n"
        )

    prompt = f"""
You are planning a single current-user PowerShell diagnostic task for a localhost helper app.

Return a structured plan. The PowerShell command is the only thing the local app will execute.

Rules:
- Return exactly one PowerShell command body. Do not wrap it in powershell.exe.
- The command must run as the current user. Do not attempt elevation, UAC,
  credential prompts, remoting, downloads, installs, or destructive deletion.
- Collect the minimum useful evidence, not exhaustive diagnostics.
- For troubleshooting requests, collect 2 to 5 relevant evidence categories
  that can prove or disprove the most likely causes.
- The command must be under {MAX_COMMAND_LENGTH} characters.
- The command must return compact structured JSON with ConvertTo-Json.
- Use short field names and small arrays. Cap lists with Select-Object -First {MAX_JSON_LIST_ITEMS}
  or an equivalent limit.
- stdout must contain evidence/result fields, not the plan.
- For install/existence/status checks, include result-oriented fields such as
  installed, found, exists, hits, paths, checked, status, version, errors, or
  inconclusive.
- For simple fact questions such as time, timezone, hostname, or current user,
  return only direct result fields such as time, local, timezone, offset,
  hostname, computerName, user, username, domain, status, or errors.
- Use valid PowerShell environment variables. For paths like Program Files (x86),
  use ${{env:ProgramFiles(x86)}}, not $env:ProgramFiles(x86).
- For missing resources such as a drive or app path, return JSON with
  exists/installed/found=false and errors; do not let the command throw.
- Do not emit diagnostic_goal, evidence_to_collect, success_criteria,
  limitations, expected_result, goal, ev, sc, lim, schema, or other planner
  metadata inside stdout.
- Do not use Format-Table, Format-List, Out-GridView, Write-Host-only output,
  or display-only formatting.
- Prefer [pscustomobject] or ordered hashtables with named fields.
- Include diagnostic_goal, evidence_to_collect, success_criteria, limitations,
  output_schema_hint, and expected_result.
- If a fact cannot be inspected reliably from PowerShell, include that as a
  limitation and collect adjacent useful evidence.
- Keep timeout_seconds between 5 and 30 unless the user explicitly asks for a long-running check.

Question the command must help answer:
What evidence would prove or disprove the likely causes of the user's issue?

{retry}
User request:
{user_request}
"""
    return llm_structured(prompt, _LocalTaskPlan)


def _prepare_plan(plan: _LocalTaskPlan | None) -> _LocalTaskPlan | None:
    if plan is None:
        return None
    plan.command = _clean_command(plan.command)
    plan.timeout_seconds = _clamp_timeout(plan.timeout_seconds)
    if not plan.summary:
        plan.summary = "Run a local PowerShell diagnostic task."
    if not plan.diagnostic_goal:
        plan.diagnostic_goal = plan.summary
    if not plan.expected_result:
        plan.expected_result = plan.output_schema_hint or "Structured diagnostic evidence."
    return plan


def _deterministic_plan(user_request: str) -> _LocalTaskPlan | None:
    text = _normalized_request_text(user_request)
    if _looks_like_time_question(text):
        return _LocalTaskPlan(
            summary="Check the current local system time and timezone.",
            risk_level="low",
            command=(
                "$now=Get-Date; $tz=Get-TimeZone; "
                "[pscustomobject]@{ok=$true;time=$now.ToString('o');"
                "local=$now.ToString('yyyy-MM-dd HH:mm:ss');"
                "date=$now.ToString('yyyy-MM-dd');"
                "timezone=$tz.Id;offset=$now.ToString('zzz');errors=@()} | "
                "ConvertTo-Json -Compress"
            ),
            timeout_seconds=5,
            diagnostic_goal="Return the current local system time and timezone.",
            evidence_to_collect=["local timestamp", "timezone", "UTC offset"],
            success_criteria=["local, timezone, and offset are present"],
            limitations=["This reports the local system clock as seen by PowerShell."],
            output_schema_hint="{ok:boolean,time:string,local:string,date:string,timezone:string,offset:string,errors:string[]}",
            expected_result="Compact JSON with current local time, date, timezone, and offset.",
        )

    if _looks_like_hostname_question(text):
        return _LocalTaskPlan(
            summary="Check the local computer name.",
            risk_level="low",
            command=(
                "[pscustomobject]@{ok=$true;hostname=$env:COMPUTERNAME;"
                "computerName=$env:COMPUTERNAME;errors=@()} | ConvertTo-Json -Compress"
            ),
            timeout_seconds=5,
            diagnostic_goal="Return the local computer name.",
            evidence_to_collect=["computer name"],
            success_criteria=["hostname is present"],
            limitations=["This reports the current user's local environment value."],
            output_schema_hint="{ok:boolean,hostname:string,computerName:string,errors:string[]}",
            expected_result="Compact JSON with the local computer name.",
        )

    if _looks_like_current_user_question(text):
        return _LocalTaskPlan(
            summary="Check the currently logged-in Windows user.",
            risk_level="low",
            command=(
                "$id=[System.Security.Principal.WindowsIdentity]::GetCurrent(); "
                "[pscustomobject]@{ok=$true;user=$id.Name;username=$env:USERNAME;"
                "domain=$env:USERDOMAIN;errors=@()} | ConvertTo-Json -Compress"
            ),
            timeout_seconds=5,
            diagnostic_goal="Return the current Windows user context.",
            evidence_to_collect=["current Windows identity", "username", "domain"],
            success_criteria=["user or username is present"],
            limitations=["This reports the user account running the local helper command."],
            output_schema_hint="{ok:boolean,user:string,username:string,domain:string,errors:string[]}",
            expected_result="Compact JSON with the current Windows user.",
        )

    if re.search(r"\b(disk\s+(space|usage|free)|free\s+space|c\s*drive)\b", text):
        drive = "C"
        match = re.search(r"\b([a-z])\s*[: ]?\s*drive\b", text)
        if match:
            drive = match.group(1).upper()
        return _LocalTaskPlan(
            summary=f"Check free and used disk space on {drive}: drive.",
            risk_level="low",
            command=(
                f"$d = Get-PSDrive -Name {drive} -ErrorAction SilentlyContinue; "
                f"$result = if ($null -eq $d) {{ "
                f"[pscustomobject]@{{Name='{drive}';Exists=$false;Error='Drive {drive}: was not found'}} "
                "} else { "
                "[pscustomobject]@{Name=$d.Name;Exists=$true;Used=$d.Used;Free=$d.Free;"
                "UsedGB=[math]::Round($d.Used/1GB,2);FreeGB=[math]::Round($d.Free/1GB,2)} "
                "}; $result | ConvertTo-Json"
            ),
            timeout_seconds=10,
            diagnostic_goal=f"Determine free and used disk space on {drive}: drive.",
            evidence_to_collect=["drive free space", "drive used space"],
            success_criteria=["FreeGB and UsedGB are present for the requested drive."],
            limitations=["This does not inspect per-folder usage."],
            output_schema_hint="Object with Name, Used, Free, UsedGB, and FreeGB.",
            expected_result="JSON with used and free disk space in bytes and GB.",
        )

    if _looks_like_steam_app_install_question(text):
        app_name = _steam_app_name(user_request)
        app_id = _steam_app_id(app_name)
        safe_app = app_name.replace("'", "''")
        manifest_name = f"appmanifest_{app_id}.acf" if app_id else ""
        folder_patterns = _steam_folder_patterns(app_name)
        quoted_patterns = [f"'{item.replace(chr(39), chr(39) + chr(39))}'" for item in folder_patterns]
        folder_array = "@(" + ",".join(quoted_patterns) + ")"
        manifest_check = (
            f"$man = if ($lib) {{ Join-Path (Join-Path $lib 'steamapps') '{manifest_name}' }} else {{ $null }}; "
            "$manifestHit = if ($man -and (Test-Path $man)) { $man } else { $null }; "
            if manifest_name
            else "$manifestHit = $null; "
        )
        return _LocalTaskPlan(
            summary=f"Check whether {app_name} is installed through Steam.",
            risk_level="low",
            command=(
                f"$app='{safe_app}'; "
                "$roots=@(); "
                "$pf=${env:ProgramFiles}; $pfx86=${env:ProgramFiles(x86)}; $local=$env:LOCALAPPDATA; "
                "foreach($root in @($pfx86,$pf,$local)){ if($root){ $roots += (Join-Path $root 'Steam') } } "
                "$libs=@(); "
                "foreach($root in $roots){ if(Test-Path $root){ $libs += $root } } "
                "foreach($root in @($roots)){ "
                "$vf=Join-Path $root 'steamapps\\libraryfolders.vdf'; "
                "if(Test-Path $vf){ "
                "$content=Get-Content $vf -Raw -ErrorAction SilentlyContinue; "
                "$matches=[regex]::Matches($content,'\"path\"\\s+\"([^\"]+)\"'); "
                "foreach($m in $matches){ $libs += ($m.Groups[1].Value -replace '\\\\\\\\','\\') } "
                "} } "
                "$libs=$libs|Where-Object{$_}|Select-Object -Unique -First 8; "
                "$hits=@(); "
                f"$patterns={folder_array}; "
                "foreach($lib in $libs){ "
                f"{manifest_check}"
                "if($manifestHit){ $hits += $manifestHit } "
                "foreach($pattern in $patterns){ "
                "$candidate=Join-Path (Join-Path $lib 'steamapps\\common') $pattern; "
                "if(Test-Path $candidate){ $hits += $candidate } "
                "} } "
                "$hits=$hits|Select-Object -Unique -First 5; "
                "[pscustomobject]@{installed=($hits.Count -gt 0); found=($hits.Count -gt 0); hits=@($hits); checked=@($libs); errors=@()} | ConvertTo-Json -Compress"
            ),
            timeout_seconds=15,
            diagnostic_goal=f"Determine whether {app_name} is installed through Steam.",
            evidence_to_collect=["Steam install locations", "Steam library folders", "app manifest or game folder"],
            success_criteria=["Return installed/found boolean", "Return hit paths when present", "Return checked locations"],
            limitations=["Only checks common current-user Steam locations and libraryfolders.vdf."],
            output_schema_hint="{installed:boolean, found:boolean, hits:string[], checked:string[], errors:string[]}",
            expected_result="Compact JSON indicating whether the Steam app was found.",
        )

    if _looks_like_microphone_availability_question(text):
        return _LocalTaskPlan(
            summary="Check whether microphone input devices are available.",
            risk_level="low",
            command=(
                "$devices=@(); "
                "$devices += Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue | "
                "Where-Object { $_.Name -match 'microphone|mic|audio input|headset' } | "
                "Select-Object -First 8 Name,Status,Manufacturer,DeviceID; "
                "$devices += Get-CimInstance Win32_SoundDevice -ErrorAction SilentlyContinue | "
                "Where-Object { $_.Name -match 'microphone|mic|audio input|headset' } | "
                "Select-Object -First 8 Name,Status,Manufacturer,DeviceID; "
                "$unique=$devices | Where-Object { $_.Name } | Sort-Object Name -Unique | Select-Object -First 8; "
                "[pscustomobject]@{available=(@($unique).Count -gt 0); found=(@($unique).Count -gt 0); devices=@($unique); checked=@('Win32_PnPEntity','Win32_SoundDevice'); errors=@()} | ConvertTo-Json -Depth 3 -Compress"
            ),
            timeout_seconds=15,
            diagnostic_goal="Determine whether microphone input devices are available.",
            evidence_to_collect=["PnP microphone-like devices", "sound device microphone-like entries"],
            success_criteria=["Return available/found boolean", "Return device names/statuses when present"],
            limitations=["PowerShell may not distinguish all physical microphones from headset/audio endpoints."],
            output_schema_hint="{available:boolean, found:boolean, devices:[{Name,Status,Manufacturer}], checked:string[], errors:string[]}",
            expected_result="Compact JSON indicating whether microphone-like input devices were found.",
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
            diagnostic_goal="Identify Windows edition, version, build, and architecture.",
            evidence_to_collect=["Windows product name", "Windows version", "OS build", "architecture"],
            success_criteria=["WindowsProductName and OsBuildNumber are present."],
            limitations=["This does not check update compliance or patch history."],
            output_schema_hint="Object with WindowsProductName, WindowsVersion, OsBuildNumber, and OsArchitecture.",
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
            diagnostic_goal="Identify the processes currently using the most memory.",
            evidence_to_collect=["process name", "process id", "memory usage in MB"],
            success_criteria=["At least one process row includes ProcessName and MemoryMB."],
            limitations=["This is a point-in-time snapshot only."],
            output_schema_hint="Array of objects with ProcessName, Id, and MemoryMB.",
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
            diagnostic_goal="Determine current physical memory usage.",
            evidence_to_collect=["total memory", "free memory", "used memory", "percent used"],
            success_criteria=["TotalGB, FreeGB, UsedGB, and UsedPct are present."],
            limitations=["This is a point-in-time snapshot only."],
            output_schema_hint="Object with TotalGB, FreeGB, UsedGB, and UsedPct.",
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
            diagnostic_goal="Determine current CPU model and load.",
            evidence_to_collect=["CPU name", "core count", "logical processor count", "load percentage"],
            success_criteria=["LoadPercentage is present for the processor."],
            limitations=["This is a point-in-time snapshot only."],
            output_schema_hint="Object or array with Name, NumberOfCores, NumberOfLogicalProcessors, and LoadPercentage.",
            expected_result="JSON with CPU model, core counts, and load percentage.",
        )

    return None


def _fallback_generic_plan(user_request: str) -> _LocalTaskPlan | None:
    terms = _extract_search_terms(user_request)
    if not terms:
        terms = ["system"]
    term_literal = _ps_array_literal(terms[:5])
    command = (
        f"$terms={term_literal}; "
        "$pattern=($terms|ForEach-Object{[regex]::Escape($_)}) -join '|'; "
        "$apps=@(); "
        "$keys=@('HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
        "'HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
        "'HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*'); "
        "foreach($key in $keys){ "
        "$apps += Get-ItemProperty $key -ErrorAction SilentlyContinue | "
        "Where-Object { $_.DisplayName -and ($_.DisplayName -match $pattern) } | "
        "Select-Object -First 8 DisplayName,DisplayVersion,Publisher,InstallLocation "
        "} "
        "$apps=$apps|Sort-Object DisplayName -Unique|Select-Object -First 8; "
        "$proc=Get-Process -ErrorAction SilentlyContinue | "
        "Where-Object { $_.ProcessName -match $pattern } | "
        "Select-Object -First 8 ProcessName,Id,@{Name='MemoryMB';Expression={[math]::Round($_.WorkingSet/1MB,1)}}; "
        "$svc=Get-CimInstance Win32_Service -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Name -match $pattern -or $_.DisplayName -match $pattern } | "
        "Select-Object -First 8 Name,DisplayName,State,StartMode; "
        "[pscustomobject]@{status='collected'; found=(@($apps).Count + @($proc).Count + @($svc).Count -gt 0); "
        "terms=@($terms); apps=@($apps); processes=@($proc); services=@($svc); "
        "checked=@('installed apps','running processes','services'); errors=@()} | ConvertTo-Json -Depth 4 -Compress"
    )
    plan = _LocalTaskPlan(
        summary="Collect compact local evidence related to the request.",
        risk_level="low",
        command=command,
        timeout_seconds=20,
        diagnostic_goal="Collect simple local evidence matching the user's request without changing the system.",
        evidence_to_collect=["installed applications", "running processes", "services"],
        success_criteria=["Return compact JSON", "Include found/status fields", "Limit results"],
        limitations=["This fallback uses keyword matching and may be inconclusive for broad or ambiguous requests."],
        output_schema_hint="{status, found, terms, apps, processes, services, checked, errors}",
        expected_result="Compact JSON with matching local applications, processes, and services.",
    )
    return plan if not _validate_plan(plan, user_request) else None


def _validate_plan(plan: _LocalTaskPlan | None, user_request: str) -> list[str]:
    if plan is None:
        return ["No structured task plan was generated."]

    errors: list[str] = []
    command = (plan.command or "").strip()
    command_lower = command.lower()
    if not command:
        errors.append("Command is empty.")
    if len(command) > MAX_COMMAND_LENGTH:
        errors.append(f"Command is too long; keep it under {MAX_COMMAND_LENGTH} characters.")
    if re.search(r"\bformat-(table|list|wide|custom)\b", command_lower):
        errors.append("Command uses display-only formatting such as Format-Table or Format-List.")
    if "out-gridview" in command_lower or "write-host" in command_lower:
        errors.append("Command uses UI/display-only output instead of structured data.")
    if re.search(r"\$env:[a-z0-9_]+\([^)]*\)", command_lower):
        errors.append("Command uses invalid PowerShell env var syntax; use ${env:Name(with-parens)}.")
    depth_error = _json_depth_error(command_lower)
    if depth_error:
        errors.append(depth_error)
    if re.search(
        r"\b(diagnostic_goal|evidence_to_collect|success_criteria|limitations|"
        r"expected_result|output_schema_hint)\b",
        command_lower,
    ):
        errors.append("Command should not emit planner metadata inside stdout.")
    metadata_error = _metadata_schema_error(plan, command_lower, user_request)
    if metadata_error:
        errors.append(metadata_error)
    if _is_diagnostic_request(user_request) and "convertto-json" not in command_lower:
        errors.append("Diagnostic command must return structured JSON using ConvertTo-Json.")
    if _is_diagnostic_request(user_request) and len(plan.evidence_to_collect or []) < 2:
        errors.append("Troubleshooting requests must collect at least two relevant evidence categories.")
    if len(plan.evidence_to_collect or []) > MAX_EVIDENCE_CATEGORIES:
        errors.append(f"Collect at most {MAX_EVIDENCE_CATEGORIES} evidence categories.")
    broad_error = _broad_command_limit_error(command_lower)
    if broad_error:
        errors.append(broad_error)
    syntax_error = _powershell_syntax_error(command)
    if syntax_error:
        errors.append(syntax_error)
    if not plan.diagnostic_goal:
        errors.append("diagnostic_goal is required.")
    if not plan.output_schema_hint:
        errors.append("output_schema_hint is required.")
    return errors


def _is_diagnostic_request(user_request: str) -> bool:
    text = _normalized_request_text(user_request)
    return bool(
        re.search(
            r"\b(not working|broken|failing|failed|issue|problem|troubleshoot|diagnos|"
            r"why|check|status|usage|slow|error|unable|can't|cannot|wont|won't)\b",
            text,
        )
    )


def _broad_command_limit_error(command_lower: str) -> str:
    broad_terms = ("get-winevent", "get-eventlog", "get-process", "get-service", "get-childitem")
    if not any(term in command_lower for term in broad_terms):
        return ""
    has_limit = any(
        token in command_lower
        for token in ("-maxevents", "-first", "select-object -first", "select -first")
    )
    if not has_limit:
        return "Broad list/event/process commands must cap results with -MaxEvents or Select-Object -First."
    return ""


def _json_depth_error(command_lower: str) -> str:
    match = re.search(r"convertto-json\s+-depth\s+(\d+)", command_lower)
    if match and int(match.group(1)) > 4:
        return "ConvertTo-Json depth must be 4 or less."
    return ""


def _powershell_syntax_error(command: str) -> str:
    if not command.strip():
        return ""
    parser_script = (
        "$code = [Console]::In.ReadToEnd(); "
        "$tokens = $null; $errors = $null; "
        "[System.Management.Automation.Language.Parser]::ParseInput($code, [ref]$tokens, [ref]$errors) | Out-Null; "
        "if ($errors.Count -gt 0) { "
        "$errors | Select-Object -First 3 | ForEach-Object { $_.Message }; exit 2 "
        "} "
        "exit 0"
    )
    for executable in ("powershell", "pwsh"):
        try:
            completed = subprocess.run(
                [
                    executable,
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    parser_script,
                ],
                input=command,
                capture_output=True,
                text=True,
                timeout=5,
                shell=False,
            )
        except FileNotFoundError:
            continue
        except Exception:
            return ""
        if completed.returncode == 0:
            return ""
        output = _clean_powershell_error(completed.stdout + "\n" + completed.stderr)
        return "PowerShell syntax validation failed: " + _truncate(output or "parser error", 220)
    return ""


def _metadata_schema_error(
    plan: _LocalTaskPlan, command_lower: str, user_request: str
) -> str:
    schema_text = " ".join(
        str(value or "").lower()
        for value in (
            plan.output_schema_hint,
            plan.expected_result,
            plan.summary,
        )
    )
    metadata_hits = _schema_key_hits(schema_text, PLANNER_METADATA_KEYS)
    result_hits = _schema_key_hits(schema_text, RESULT_ORIENTED_KEYS)

    metadata_assignments = _metadata_assignment_hits(command_lower)
    if len(metadata_assignments) >= 2:
        return "Command appears to emit planner metadata instead of result fields."

    compact_metadata_aliases = _schema_key_hits(command_lower, {"goal", "ev", "sc", "lim", "schema"})
    if len(compact_metadata_aliases) >= 4 and not _schema_key_hits(command_lower, RESULT_ORIENTED_KEYS):
        return "Command appears to emit planner metadata instead of result fields."

    if len(metadata_hits) >= 3 and len(metadata_hits) > len(result_hits):
        return "stdout schema is mostly planner metadata; return concrete result/evidence fields instead."

    if _is_direct_answer_request(user_request) and not (
        result_hits or _schema_key_hits(command_lower, RESULT_ORIENTED_KEYS)
    ):
        return "Generic checks must return result fields such as installed, found, exists, hits, status, version, errors, or inconclusive."

    return ""


def _schema_key_hits(text: str, keys: set[str]) -> set[str]:
    hits: set[str] = set()
    for key in keys:
        if re.search(rf"(?<![a-z0-9_]){re.escape(key.lower())}(?![a-z0-9_])", text):
            hits.add(key)
    return hits


def _metadata_assignment_hits(command_lower: str) -> set[str]:
    hits: set[str] = set()
    for key in {"goal", "ev", "sc", "lim", "schema"}:
        if re.search(rf"(\.\s*{key}\s*=|['\"]{key}['\"]\s*=|{key}\s*=)", command_lower):
            hits.add(key)
    return hits


def _summarize_local_result(pending: Dict[str, Any], result: Dict[str, Any]) -> str:
    status = result.get("status") or "unknown"
    needs_elevation = bool(result.get("needs_elevation"))
    stdout = str(result.get("stdout") or "")
    stderr = _truncate(str(result.get("stderr") or ""), 1000)
    message = result.get("message") or "The local task returned a result."

    if needs_elevation:
        return (
            f"{message} This appears to require administrator privileges. "
            "I did not attempt elevation because the local app runs as the current user."
        )

    if status == "complete":
        interpreted = _interpret_successful_output(pending, stdout)
        if interpreted:
            return interpreted
        return _summarize_generic_success(pending, stdout, message)
    if status == "timeout":
        return message or "The local task timed out before it finished."
    failure_summary = _summarize_failed_result(pending, result)
    if failure_summary:
        return failure_summary
    details = _clean_powershell_error(stderr or stdout or message)
    return f"Local task status: {status}. {_truncate(details, MAX_CHAT_EXCERPT)}".strip()


def _clean_command(command: str) -> str:
    command = (command or "").strip()
    command = re.sub(r"^```(?:powershell|ps1|pwsh)?", "", command, flags=re.I).strip()
    command = re.sub(r"```$", "", command).strip()
    return command


def _interpret_successful_output(pending: Dict[str, Any], stdout: str) -> str:
    data = _parse_json_output(stdout)
    command = str(pending.get("command") or "")
    summary = str(pending.get("summary") or "Local task")

    if isinstance(data, dict):
        for summarizer in (
            _summarize_disk,
            _summarize_windows_version,
            _summarize_memory,
            _summarize_cpu,
        ):
            summary_text = summarizer(data)
            if summary_text:
                return summary_text
        direct_answer = _summarize_direct_answer(pending, data)
        if direct_answer:
            return direct_answer
        simple_fact = _summarize_simple_fact(pending, data)
        if simple_fact:
            return simple_fact
        return _summarize_unknown_json(pending, data)

    if isinstance(data, list):
        process_summary = _summarize_processes(data)
        if process_summary:
            return process_summary
        direct_answer = _summarize_direct_answer(pending, data)
        if direct_answer:
            return direct_answer
        simple_fact = _summarize_simple_fact(pending, data)
        if simple_fact:
            return simple_fact
        return _summarize_unknown_json(pending, data)

    if stdout.strip():
        return _summarize_generic_success(pending, stdout, "The command completed.")
    if command:
        return f"{summary}\n\nThe local app completed the command successfully."
    return ""


def _summarize_failed_result(pending: Dict[str, Any], result: Dict[str, Any]) -> str:
    user_request = str(pending.get("user_request") or "").strip()
    text = _clean_powershell_error(
        "\n".join(
            str(value or "")
            for value in (
                result.get("stderr"),
                result.get("stdout"),
                result.get("message"),
                " ".join(str(item) for item in result.get("errors") or []),
            )
        )
    )
    lower = text.lower()

    drive = _requested_drive(user_request)
    if drive and ("cannot find drive" in lower or "drive with the name" in lower or "drivenotfound" in lower):
        return f"Drive {drive}: was not found on this system, so I could not report disk space for it."

    if "unexpected token" in lower or "parsererror" in lower:
        return (
            "The local PowerShell command failed because the generated command had "
            "a syntax error. I could not determine the answer from that run."
        )

    if "access is denied" in lower or "requires elevation" in lower:
        return (
            "The local command could not access the required information with the "
            "current user permissions. I did not attempt administrator elevation."
        )

    if _is_direct_answer_request(user_request):
        target = _answer_target(user_request)
        return (
            f"I could not determine whether {target} {_target_condition(user_request)} "
            f"because the local command failed. Reason: {_truncate(text, 220)}"
        )

    return ""


def _looks_like_powershell_syntax_failure(text: str) -> bool:
    lower = (text or "").lower()
    return any(
        marker in lower
        for marker in (
            "unexpected token",
            "parsererror",
            "parseexception",
            "missing closing",
            "terminator expected",
            "missing expression",
            "incomplete string token",
            "unexpected end",
        )
    )


def _summarize_generic_success(
    pending: Dict[str, Any], stdout: str, message: str
) -> str:
    user_request = str(pending.get("user_request") or "").strip()
    summary = str(pending.get("summary") or "Local task").strip()
    diagnostic_goal = str(pending.get("diagnostic_goal") or "").strip()
    evidence = _as_text_list(pending.get("evidence_to_collect"))
    criteria = _as_text_list(pending.get("success_criteria"))
    limitations = _as_text_list(pending.get("limitations"))
    output = (stdout or "").strip()

    intro = summary
    if user_request:
        intro = f"For your request, \"{user_request}\", I ran: {summary}"

    details = []
    if diagnostic_goal:
        details.append(_sentence(f"Checked: {diagnostic_goal}"))
    if output:
        if _looks_like_structured_text(output):
            details.append(
                "Found: The command returned structured output, but it could not be "
                "parsed cleanly enough to summarize without showing raw data."
            )
        else:
            details.append(f"Found: {_truncate(output, MAX_CHAT_EXCERPT)}")
    else:
        details.append(_sentence(f"Found: {message or 'The command completed successfully'}"))
    if criteria:
        details.append("Likely meaning: Use these criteria to judge the result: " + "; ".join(criteria[:3]))
    if limitations:
        details.append("Next step: Review the result with this limitation in mind: " + limitations[0])
    elif evidence:
        details.append("Next step: Run a narrower follow-up check if the issue is still unclear.")

    return intro + "\n\n" + "\n".join(details)


def _parse_json_output(stdout: str) -> Any:
    text = (stdout or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _summarize_direct_answer(pending: Dict[str, Any], data: Any) -> str:
    user_request = str(pending.get("user_request") or "").strip()
    is_direct_request = _is_direct_answer_request(user_request)
    is_status_request = _is_simple_status_request(user_request)
    if not is_direct_request and not is_status_request:
        return ""

    target = _answer_target(user_request)
    if _is_metadata_only(data):
        return (
            "The command ran, but it did not return enough evidence to answer "
            f"whether {target} {_target_condition(user_request)}."
        )

    flattened = _flatten_result_records(data)
    if not flattened:
        return (
            "I could not determine "
            f"whether {target} {_target_condition(user_request)} from the returned output."
        )

    if is_status_request and not is_direct_request:
        return _summarize_status_answer(target, flattened)

    explicit_state = _explicit_presence_state(flattened)
    hits = _result_values(flattened, {"hits", "paths", "path", "manifest", "manifests", "location", "locations", "devices", "device"})
    checked = _result_values(flattened, {"checked", "checked_paths", "checkedlocations", "libraries", "libs"})
    errors = _result_values(flattened, {"errors", "error"})
    version = _first_result_value(flattened, {"version"})
    status = _first_result_value(flattened, {"status"})
    inconclusive = _truthy_field(flattened, {"inconclusive"})

    if explicit_state is True or hits:
        evidence = _evidence_sentence("Evidence", hits or ([version] if version else []))
        suffix = f" {evidence}" if evidence else ""
        version_text = f" Version found: {_truncate(str(version), 160)}." if version else ""
        return f"Yes, {target} appears to be {_target_state(user_request)}.{suffix}{version_text}".strip()

    if explicit_state is False and not inconclusive:
        evidence = _evidence_sentence("Checked", checked)
        suffix = f" {evidence}" if evidence else ""
        return f"I did not find evidence that {target} {_target_condition(user_request)}.{suffix}".strip()

    reason = ""
    if errors:
        reason = " Reason: " + "; ".join(_truncate(str(item), 160) for item in errors[:2])
    elif status:
        reason = f" Status returned: {_truncate(str(status), 160)}."
    return (
        f"I could not determine whether {target} {_target_condition(user_request)} from "
        f"the returned output.{reason}"
    ).strip()


def _is_direct_answer_request(user_request: str) -> bool:
    text = _normalized_request_text(user_request)
    return bool(
        re.search(
            r"\b(install(ed)?|do i have|does my (system|pc|computer|machine) "
            r"(have|has)|is .+ (installed|present|available)|exists?|found|"
            r"available|present|check whether|check if)\b",
            text,
        )
    )


def _is_simple_status_request(user_request: str) -> bool:
    text = _normalized_request_text(user_request)
    if re.search(r"\b(not working|broken|failing|failed|issue|problem|troubleshoot|diagnos)\b", text):
        return False
    return bool(re.search(r"\b(status of|check .+ status|is .+ running|running status)\b", text))


def _is_metadata_only(data: Any) -> bool:
    if not isinstance(data, dict) or not data:
        return False
    keys = {str(key).lower() for key in data}
    metadata_count = len(keys & PLANNER_METADATA_KEYS)
    result_count = len(keys & RESULT_ORIENTED_KEYS)
    return metadata_count >= 2 and result_count == 0


def _flatten_result_records(data: Any) -> list[tuple[str, Any]]:
    records: list[tuple[str, Any]] = []
    if isinstance(data, dict):
        for key, value in data.items():
            key_text = str(key).lower()
            if key_text in PLANNER_METADATA_KEYS:
                continue
            if isinstance(value, dict):
                records.extend(_flatten_result_records(value))
            elif isinstance(value, list):
                if key_text in RESULT_ORIENTED_KEYS:
                    records.append((key_text, value))
                for item in value:
                    if isinstance(item, (dict, list)):
                        records.extend(_flatten_result_records(item))
            else:
                records.append((key_text, value))
    elif isinstance(data, list):
        for item in data:
            records.extend(_flatten_result_records(item))
    return records


def _explicit_presence_state(records: list[tuple[str, Any]]) -> bool | None:
    state_by_key: dict[str, bool] = {}
    for key, value in records:
        if key in {"installed", "found", "exists", "present", "available", "detected"}:
            if isinstance(value, bool):
                state_by_key[key] = value
            elif isinstance(value, str) and value.strip().lower() in {"true", "yes", "present", "found", "installed"}:
                state_by_key[key] = True
            elif isinstance(value, str) and value.strip().lower() in {"false", "no", "missing", "not found", "not installed"}:
                state_by_key[key] = False
            elif isinstance(value, (int, float)) and key in {"found", "available", "detected"}:
                state_by_key[key] = value > 0
    for key in ("available", "detected", "found", "exists", "present", "installed"):
        if key in state_by_key:
            return state_by_key[key]
    return None


def _truthy_field(records: list[tuple[str, Any]], keys: set[str]) -> bool:
    for key, value in records:
        if key in keys and value not in (None, "", False, [], {}):
            return True
    return False


def _result_values(records: list[tuple[str, Any]], keys: set[str]) -> list[Any]:
    values: list[Any] = []
    for key, value in records:
        normalized = key.replace("_", "")
        normalized_keys = {item.replace("_", "") for item in keys}
        if key not in keys and normalized not in normalized_keys:
            continue
        if isinstance(value, list):
            values.extend(item for item in value if item not in (None, "", [], {}))
        elif value not in (None, "", [], {}):
            values.append(value)
    return values[:MAX_JSON_LIST_ITEMS]


def _first_result_value(records: list[tuple[str, Any]], keys: set[str]) -> Any:
    values = _result_values(records, keys)
    return values[0] if values else None


def _summarize_status_answer(target: str, records: list[tuple[str, Any]]) -> str:
    status = _first_result_value(records, {"status", "state"})
    version = _first_result_value(records, {"version"})
    errors = _result_values(records, {"errors", "error"})
    hits = _result_values(records, {"hits", "paths", "path", "location", "locations"})

    if not any((status, version, errors, hits)):
        return f"I could not determine the status of {target} from the returned output."

    parts = [f"Status for {target}: {_truncate(str(status), 160)}." if status else f"I checked {target}."]
    if version:
        parts.append(f"Version: {_truncate(str(version), 160)}.")
    if hits:
        parts.append(_evidence_sentence("Evidence", hits))
    if errors:
        parts.append("Errors: " + "; ".join(_truncate(str(item), 160) for item in errors[:2]) + ".")
    return " ".join(part for part in parts if part)


def _summarize_simple_fact(pending: Dict[str, Any], data: Any) -> str:
    user_request = str(pending.get("user_request") or "").strip()
    text = _normalized_request_text(user_request)
    if not _is_simple_fact_request(text):
        return ""
    if _is_metadata_only(data):
        return "The command ran, but it did not return enough evidence to answer your question."

    flattened = _flatten_result_records(data)
    if not flattened:
        return "I could not determine the answer from the returned output."

    errors = _result_values(flattened, {"errors", "error"})
    if _looks_like_time_question(text):
        local = _first_result_value(flattened, {"local", "time"})
        timezone = _first_result_value(flattened, {"timezone", "tz"})
        offset = _first_result_value(flattened, {"offset", "utc_offset"})
        date = _first_result_value(flattened, {"date"})
        if local:
            suffix = _timezone_suffix(timezone, offset)
            return f"The current system time is {_truncate(str(local), 120)}{suffix}."
        if timezone and re.search(r"\b(timezone|time\s+zone)\b", text):
            return f"The system timezone is {_timezone_value(timezone, offset)}."
        if date:
            return f"The current system date is {_truncate(str(date), 120)}."
        return _inconclusive_simple_fact(errors)

    if _looks_like_hostname_question(text):
        hostname = _first_result_value(flattened, {"hostname", "computername", "computer_name", "machine", "name"})
        if hostname:
            return f"The computer name is {_truncate(str(hostname), 160)}."
        return _inconclusive_simple_fact(errors)

    if _looks_like_current_user_question(text):
        user = _first_result_value(flattened, {"user", "username"})
        domain = _first_result_value(flattened, {"domain"})
        if user and domain and "\\" not in str(user):
            return f"The current Windows user is {domain}\\{user}."
        if user:
            return f"The current Windows user is {_truncate(str(user), 180)}."
        return _inconclusive_simple_fact(errors)

    fields = _simple_fact_fields(flattened)
    if fields:
        target = _simple_fact_target(user_request)
        finding = "; ".join(f"{label}: {_truncate(_format_evidence_value(value), 160)}" for label, value in fields[:3])
        if target:
            return f"{target}: {finding}."
        return f"I found: {finding}."
    return _inconclusive_simple_fact(errors)


def _inconclusive_simple_fact(errors: list[Any]) -> str:
    if errors:
        return "I could not determine the answer. Reason: " + "; ".join(
            _truncate(str(item), 160) for item in errors[:2]
        ) + "."
    return "I could not determine the answer from the returned output."


def _timezone_suffix(timezone: Any, offset: Any) -> str:
    parts = []
    if timezone:
        parts.append(str(timezone))
    if offset:
        offset_text = str(offset)
        if not offset_text.upper().startswith("UTC"):
            offset_text = "UTC" + offset_text
        parts.append(offset_text)
    return f" ({', '.join(parts)})" if parts else ""


def _timezone_value(timezone: Any, offset: Any) -> str:
    value = _truncate(str(timezone), 120) if timezone else "unknown"
    if offset:
        offset_text = str(offset)
        if not offset_text.upper().startswith("UTC"):
            offset_text = "UTC" + offset_text
        value += f" ({offset_text})"
    return value


def _simple_fact_fields(records: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
    skip = {"ok", "errors", "error", "checked"}
    fields: list[tuple[str, Any]] = []
    for key, value in records:
        if key in skip or value in (None, "", [], {}):
            continue
        if isinstance(value, list):
            preview = [item for item in value if item not in (None, "", [], {})][:MAX_JSON_LIST_ITEMS]
            if preview:
                fields.append((_humanize_key(key), preview))
        else:
            fields.append((_humanize_key(key), value))
        if len(fields) >= MAX_EVIDENCE_CATEGORIES:
            break
    return fields


def _humanize_key(key: str) -> str:
    key = re.sub(r"([a-z])([A-Z])", r"\1 \2", key)
    return key.replace("_", " ").strip().title()


def _simple_fact_target(user_request: str) -> str:
    text = re.sub(r"[?.!]+$", "", user_request.strip())
    match = re.search(r"\b(?:what is|what are|show me|show|tell me|check)\s+(?:the\s+)?(.+)$", text, flags=re.I)
    if match:
        return _sentence(match.group(1).strip())
    return ""


def _evidence_sentence(label: str, values: list[Any]) -> str:
    if not values:
        return ""
    preview = "; ".join(_truncate(_format_evidence_value(value), 180) for value in values[:2])
    return f"{label}: {preview}."


def _format_evidence_value(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("Name", "name", "Device", "device", "Path", "path", "Status", "status"):
            if value.get(key):
                status = value.get("Status") or value.get("status")
                if status and key.lower() != "status":
                    return f"{value.get(key)} ({status})"
                return str(value.get(key))
        return ", ".join(f"{key}={val}" for key, val in list(value.items())[:3])
    return str(value)


def _answer_target(user_request: str) -> str:
    text = re.sub(r"[?.!]+$", "", _normalized_request_text(user_request).strip())
    patterns = (
        r"\bwhat\s+(?:is|are)\s+(?:the\s+)?(.+?)\s+(?:available|present)\b",
        r"\b(?:is|are)\s+(.+?)\s+(?:installed|present|available)\b",
        r"\bcheck\s+(.+?)\s+status\b",
        r"\bstatus\s+of\s+(.+?)$",
        r"\bis\s+(.+?)\s+running\b",
        r"\b(?:do i have|does my (?:system|pc|computer|machine) (?:have|has))\s+(.+?)(?:\s+installed)?$",
        r"\bcheck\s+(?:whether|if)\s+(.+?)\s+(?:is\s+)?(?:installed|present|available|exists?)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return _clean_target(match.group(1))
    return "the requested item"


def _clean_target(value: str) -> str:
    target = re.sub(r"\b(on|in)\s+(my|this)\s+(system|pc|computer|machine)$", "", value, flags=re.I).strip()
    target = re.sub(r"\s+", " ", target)
    return target or "the requested item"


def _target_condition(user_request: str) -> str:
    text = _normalized_request_text(user_request)
    if "install" in text:
        return "is installed"
    if "available" in text:
        return "is available"
    if "exist" in text:
        return "exists"
    return "is present"


def _target_state(user_request: str) -> str:
    condition = _target_condition(user_request)
    if condition.startswith("is "):
        return condition.removeprefix("is ")
    return "present"


def _normalized_request_text(user_request: str) -> str:
    text = (user_request or "").lower()
    replacements = {
        "michrophone": "microphone",
        "microfone": "microphone",
        "micophone": "microphone",
        "avaliable": "available",
        "availabe": "available",
        "avialable": "available",
        "dota2": "dota 2",
    }
    for wrong, right in replacements.items():
        text = text.replace(wrong, right)
    return text


def _extract_search_terms(user_request: str) -> list[str]:
    text = _normalized_request_text(user_request)
    stop_words = {
        "what",
        "which",
        "where",
        "when",
        "why",
        "how",
        "the",
        "this",
        "that",
        "with",
        "from",
        "have",
        "has",
        "does",
        "system",
        "computer",
        "machine",
        "installed",
        "install",
        "available",
        "present",
        "working",
        "status",
        "check",
        "show",
        "list",
        "local",
        "device",
        "please",
        "help",
    }
    terms: list[str] = []
    for token in re.findall(r"[a-z0-9][a-z0-9_.-]{2,}", text):
        if token in stop_words or token in terms:
            continue
        terms.append(token)
        if len(terms) >= 5:
            break
    return terms


def _ps_array_literal(values: list[str]) -> str:
    if not values:
        return "@()"
    quoted = []
    for value in values:
        safe = re.sub(r"[^a-zA-Z0-9_. -]", "", value).strip()
        if not safe:
            continue
        quoted.append("'" + safe.replace("'", "''") + "'")
    return "@(" + ",".join(quoted or ["'system'"]) + ")"


def _requested_drive(user_request: str) -> str:
    text = _normalized_request_text(user_request)
    match = re.search(r"\b([a-z])\s*[: ]?\s*drive\b", text)
    if match:
        return match.group(1).upper()
    return ""


def _clean_powershell_error(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"^#<\s*CLIXML\s*", "", text, flags=re.I).strip()
    text = re.sub(r"<S S=\"Error\">", "\n", text)
    text = re.sub(r"</S>", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    replacements = {
        "_x000D__x000A_": "\n",
        "&lt;": "<",
        "&gt;": ">",
        "&amp;": "&",
        "&quot;": '"',
        "&apos;": "'",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    lines: list[str] = []
    for line in text.splitlines():
        clean = re.sub(r"\s+", " ", line).strip()
        if clean and clean not in lines:
            lines.append(clean)
    return "\n".join(lines[:6])


def _looks_like_steam_app_install_question(text: str) -> bool:
    return bool(
        re.search(r"\b(install(ed)?|do i have|does my .+ have|is .+ installed)\b", text)
        and re.search(r"\b(dota\s*2|dota|steam)\b", text)
    )


def _steam_app_name(user_request: str) -> str:
    text = _normalized_request_text(user_request)
    if re.search(r"\bdota\s*2\b|\bdota\b", text):
        return "DOTA2"
    match = re.search(r"\b(?:is|have|has)\s+(.+?)\s+installed\b", text)
    if match:
        return _clean_target(match.group(1)).upper()
    return "the requested Steam app"


def _steam_app_id(app_name: str) -> str:
    normalized = app_name.lower().replace(" ", "")
    known = {
        "dota": "570",
        "dota2": "570",
    }
    return known.get(normalized, "")


def _steam_folder_patterns(app_name: str) -> list[str]:
    normalized = app_name.lower().replace(" ", "")
    if normalized in {"dota", "dota2"}:
        return ["dota 2 beta", "Dota 2 Beta", "dota 2", "DOTA2"]
    return [app_name]


def _looks_like_microphone_availability_question(text: str) -> bool:
    return bool(
        re.search(r"\b(microphone|mic)\b", text)
        and re.search(r"\b(available|present|connected|detected|installed|what|which|list|show|check)\b", text)
    )


def _looks_like_time_question(text: str) -> bool:
    return bool(
        re.search(
            r"\b(current\s+)?(system\s+)?(time|date|datetime|date\s+and\s+time|timezone|time\s+zone)\b",
            text,
        )
        or re.search(r"\bwhat\s+(time|date)\b", text)
    )


def _looks_like_hostname_question(text: str) -> bool:
    return bool(
        re.search(
            r"\b(host\s*name|hostname|computer\s+name|pc\s+name|machine\s+name|device\s+name)\b",
            text,
        )
    )


def _looks_like_current_user_question(text: str) -> bool:
    return bool(
        re.search(
            r"\b(current\s+user|logged\s+in\s+user|signed\s+in\s+user|who\s+am\s+i|username|user\s+name)\b",
            text,
        )
    )


def _is_simple_fact_request(text: str) -> bool:
    if re.search(r"\b(not working|broken|failing|failed|issue|problem|troubleshoot|diagnos|fix|repair)\b", text):
        return False
    if _looks_like_time_question(text) or _looks_like_hostname_question(text) or _looks_like_current_user_question(text):
        return True
    return bool(re.search(r"\b(what is|what are|show me|tell me|current|check)\b", text))


def _is_troubleshooting_request(text: str) -> bool:
    return bool(re.search(r"\b(not working|broken|failing|failed|issue|problem|troubleshoot|diagnos|fix|repair|slow|crash|hang|error)\b", text))


def _looks_like_structured_text(value: str) -> bool:
    text = (value or "").strip()
    return text.startswith("{") or text.startswith("[")


def _summarize_unknown_json(pending: Dict[str, Any], data: Any) -> str:
    user_request = str(pending.get("user_request") or "the request").strip()
    text = _normalized_request_text(user_request)
    diagnostic_goal = str(pending.get("diagnostic_goal") or pending.get("summary") or "").strip()
    evidence = _as_text_list(pending.get("evidence_to_collect"))
    criteria = _as_text_list(pending.get("success_criteria"))
    limitations = _as_text_list(pending.get("limitations"))

    if _is_metadata_only(data):
        return (
            "The command ran, but it did not return enough evidence to answer "
            "your question."
        )

    findings = _compact_findings(data)
    if not _is_troubleshooting_request(text):
        if findings:
            return "I found: " + "; ".join(findings[:MAX_EVIDENCE_CATEGORIES]) + "."
        return "The command returned structured output, but I could not determine a clear answer from it."

    checked = "; ".join(evidence[:MAX_EVIDENCE_CATEGORIES]) or _top_level_summary(data)
    found = "; ".join(findings[:MAX_EVIDENCE_CATEGORIES]) or "Structured evidence was returned, but no obvious finding could be summarized automatically."
    likely = "The backend received local evidence and interpreted it against the requested diagnostic goal."
    if criteria:
        likely = "Use these criteria to judge the result: " + "; ".join(criteria[:3])
    next_step = "Review the findings above and run a narrower follow-up check if the issue is still unclear."
    if limitations:
        next_step += " Limitation: " + limitations[0]

    lines = [
        f"For your request, \"{user_request}\":",
        _sentence(f"Checked: {checked}"),
        _sentence(f"Found: {found}"),
        f"Likely meaning: {likely}",
        f"Next step: {next_step}",
    ]
    if diagnostic_goal:
        lines.insert(1, _sentence(f"Goal: {diagnostic_goal}"))
    return "\n".join(lines)


def _compact_findings(data: Any, prefix: str = "") -> list[str]:
    findings: list[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            if str(key).lower() in PLANNER_METADATA_KEYS:
                continue
            label = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, dict):
                findings.extend(_compact_findings(value, label))
            elif isinstance(value, list):
                findings.append(f"{label}: {len(value)} item(s)")
            elif value not in (None, "", []):
                findings.append(f"{label}: {_truncate(str(value), 120)}")
            if len(findings) >= MAX_EVIDENCE_CATEGORIES:
                break
    elif isinstance(data, list):
        findings.append(f"returned {len(data)} item(s)")
        for idx, item in enumerate(data[:MAX_JSON_LIST_ITEMS], start=1):
            if isinstance(item, dict):
                small = {
                    key: value
                    for key, value in list(item.items())[:3]
                    if value not in (None, "", [])
                }
                findings.append(f"item {idx}: {small}")
            else:
                findings.append(f"item {idx}: {_truncate(str(item), 120)}")
            if len(findings) >= MAX_EVIDENCE_CATEGORIES:
                break
    return findings


def _top_level_summary(data: Any) -> str:
    if isinstance(data, dict):
        keys = list(data.keys())[:MAX_EVIDENCE_CATEGORIES]
        return "top-level fields: " + ", ".join(str(key) for key in keys)
    if isinstance(data, list):
        return f"{len(data)} returned item(s)"
    return "structured output"


def _summarize_disk(data: Dict[str, Any]) -> str:
    if data.get("Exists") is False or data.get("exists") is False:
        drive = data.get("Name") or data.get("name") or "the requested drive"
        return f"Drive {drive}: was not found on this system, so I could not report disk space for it."
    if "Name" not in data or not ({"UsedGB", "FreeGB"} & set(data)):
        return ""
    drive = data.get("Name") or "the drive"
    used_gb = data.get("UsedGB")
    free_gb = data.get("FreeGB")
    total_gb = None
    try:
        if used_gb is not None and free_gb is not None:
            total_gb = round(float(used_gb) + float(free_gb), 2)
    except Exception:
        total_gb = None

    parts = [f"Drive {drive}: has {free_gb} GB free and {used_gb} GB used."]
    if total_gb is not None:
        parts.append(f"Total size is about {total_gb} GB.")
    return " ".join(parts)


def _summarize_windows_version(data: Dict[str, Any]) -> str:
    product = data.get("WindowsProductName")
    version = data.get("WindowsVersion")
    build = data.get("OsBuildNumber")
    arch = data.get("OsArchitecture")
    if not any((product, version, build, arch)):
        return ""
    bits = ["Windows version check complete."]
    if product:
        bits.append(f"Edition: {product}.")
    if version:
        bits.append(f"Version: {version}.")
    if build:
        bits.append(f"Build: {build}.")
    if arch:
        bits.append(f"Architecture: {arch}.")
    return " ".join(bits)


def _summarize_memory(data: Dict[str, Any]) -> str:
    if not {"TotalGB", "FreeGB", "UsedGB", "UsedPct"} & set(data):
        return ""
    return (
        "Memory usage check complete. "
        f"Total memory: {data.get('TotalGB')} GB. "
        f"Used: {data.get('UsedGB')} GB ({data.get('UsedPct')}%). "
        f"Free: {data.get('FreeGB')} GB."
    )


def _summarize_cpu(data: Dict[str, Any]) -> str:
    if not {"Name", "NumberOfCores", "NumberOfLogicalProcessors", "LoadPercentage"} & set(data):
        return ""
    return (
        "CPU usage check complete. "
        f"Processor: {data.get('Name')}. "
        f"Cores: {data.get('NumberOfCores')}; logical processors: {data.get('NumberOfLogicalProcessors')}. "
        f"Current load: {data.get('LoadPercentage')}%."
    )


def _summarize_processes(data: list[Any]) -> str:
    rows = [item for item in data if isinstance(item, dict)]
    if not rows or not any("ProcessName" in row for row in rows):
        return ""
    top = []
    for row in rows[:5]:
        name = row.get("ProcessName") or "unknown"
        memory = row.get("MemoryMB")
        pid = row.get("Id")
        if memory is not None:
            top.append(f"{name} (PID {pid}, {memory} MB)")
        else:
            top.append(f"{name} (PID {pid})")
    return "Top memory-consuming processes: " + "; ".join(top) + "."


def _interpretation_hint_for_plan(plan: _LocalTaskPlan) -> str:
    expected = (plan.expected_result or "").lower()
    summary = (plan.summary or "").lower()
    command = (plan.command or "").lower()

    if "disk" in expected or "disk" in summary or "get-psdrive" in command:
        return "Explain free and used disk space in GB and mention the drive."
    if "windows" in expected or "windows" in summary or "get-computerinfo" in command:
        return "Explain Windows edition, version, build, and architecture."
    if "memory" in expected or "memory" in summary:
        return "Explain total, used, free memory, and percentage used."
    if "cpu" in expected or "cpu" in summary or "win32_processor" in command:
        return "Explain CPU model, core count, logical processor count, and load."
    if "process" in expected or "process" in summary or "get-process" in command:
        return "Summarize the top relevant processes and their memory usage."
    return "Use the original user request and command output to answer in plain language."


def _as_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _is_activation_phrase(message: str) -> bool:
    return bool(
        re.fullmatch(
            r"\s*(local\s+system\s+agent|local\s+agent|system\s+agent)\s*",
            message or "",
            flags=re.I,
        )
    )


def _is_protocol_message(message: str) -> bool:
    return (message or "").strip().lower() in {
        "browser diagnostics ready",
        "local app action complete",
        "local app action failed",
    }


def _sentence(value: str) -> str:
    text = value.strip()
    if text.endswith((".", "!", "?")):
        return text
    return text + "."


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
