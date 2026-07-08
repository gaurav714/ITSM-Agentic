import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import ChatWindow from "../components/ChatWindow.jsx";
import ChatInput from "../components/ChatInput.jsx";
import ConfirmationModal from "../components/ConfirmationModal.jsx";
import { useConversationStore } from "../store/useConversationStore.js";
import { listWorkflows, sendAgentMessage, startWorkflow } from "../api/agentApi.js";
import { API_BASE_URL, API_LOCAL_FALLBACK_URL } from "../api/client.js";
import {
  submitBrowserDiagnostics,
  submitLocalActionResult,
} from "../api/diagnosticApi.js";
import {
  collectBrowserDiagnostics,
  executeLocalAppAction,
} from "../utils/browserDiagnostics.js";

export default function ConversationPage() {
  const { workflowId } = useParams();
  const navigate = useNavigate();
  const {
    sessionId,
    messages,
    cards,
    workflow,
    state,
    loading,
    addUserMessage,
    addAssistantResponse,
    setLoading,
  } = useConversationStore();

  const startedRef = useRef(null);
  const reasoningEndRef = useRef(null);
  const [pendingLocalAction, setPendingLocalAction] = useState(null);

  useEffect(() => {
    if (!workflowId) return;
    if (startedRef.current === workflowId) return;
    startedRef.current = workflowId;
    (async () => {
      setLoading(true);
      try {
        const resp = await startWorkflow(sessionId, workflowId);
        addAssistantResponse(resp);
        await maybeAutoSubmitBrowserDiagnostics(
          resp,
          sessionId,
          addAssistantResponse,
        );
        await maybeAutoExecuteLocalAppAction(
          resp,
          sessionId,
          addAssistantResponse,
          setPendingLocalAction,
        );
      } catch (e) {
        addAssistantResponse({
          message: formatAssistantError(e, "starting the workflow"),
          cards: [],
        });
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId]);

  const handleSend = async (text) => {
    addUserMessage(text);
    setLoading(true);
    try {
      const resp = await sendAgentMessage(sessionId, text);
      addAssistantResponse(resp);
      await maybeAutoSubmitBrowserDiagnostics(
        resp,
        sessionId,
        addAssistantResponse,
      );
      await maybeAutoExecuteLocalAppAction(
        resp,
        sessionId,
        addAssistantResponse,
        setPendingLocalAction,
      );
    } catch (e) {
      addAssistantResponse({
        message: formatAssistantError(e, "contacting the assistant"),
        cards: [],
      });
    } finally {
      setLoading(false);
    }
  };

  const latestTicket = [...cards]
    .reverse()
    .find((card) => card.kind === "ticket_created" || card.kind === "ticket_draft");
  const latestDiagnostic = [...cards]
    .reverse()
    .find((card) => card.kind === "diagnostic_result" || card.kind === "diagnostic_status");
  const automationProgress = getAutomationProgress(state, cards);
  const workflowLabel = workflow ? workflow.replaceAll("_", " ") : "Password Reset";
  const agentReasoningItems = getAgentReasoningItems(cards, latestDiagnostic);

  useEffect(() => {
    reasoningEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [agentReasoningItems.length, messages.length, cards.length, loading]);

  return (
    <div className="h-full overflow-hidden bg-white">
      <ConfirmationModal
        open={Boolean(pendingLocalAction)}
        title="Approve local system action"
        highlightMessage={
          pendingLocalAction
            ? "The agent wants to run a command on your local device. Review it before approving."
            : ""
        }
        message={confirmationMessage(pendingLocalAction)}
        detailLabel={pendingLocalAction?.command ? "PowerShell command" : ""}
        detailText={pendingLocalAction?.command || ""}
        onCancel={() => {
          setPendingLocalAction(null);
          addAssistantResponse({
            message: "Local action cancelled. Nothing was run on this workstation.",
            workflow,
            state,
            cards: [],
          });
        }}
        onConfirm={async () => {
          const actionRequest = pendingLocalAction;
          setPendingLocalAction(null);
          setLoading(true);
          try {
            await executeAndSubmitLocalAction(
              actionRequest,
              sessionId,
              addAssistantResponse,
            );
          } finally {
            setLoading(false);
          }
        }}
      />
      <div className="mx-auto flex h-full w-full max-w-[1440px] flex-col px-4 pb-5 sm:px-6 lg:px-[60px]">
        <section className="mb-5 shrink-0 rounded-b-xl bg-slate-100 px-6 py-3 text-slate-800">
          <p className="text-base leading-7">
            Fully automated ITSM assistance with diagnostics, ticket drafting,
            and live workflow telemetry in one operational console.
          </p>
        </section>
        <MobileWorkflowLauncher onSelect={(id) => navigate(`/chat/${id}`)} />

        <section className="grid min-h-0 flex-1 gap-4 overflow-hidden lg:grid-cols-[1.05fr_1.05fr_1fr]">
          <Panel
            icon="spark"
            iconTone="from-indigo-500 to-brand"
            title="Zoé · IT Assistant"
            subtitle={toTitleCase(workflowLabel)}
            status={<StatusPill tone="emerald" label={loading ? "working" : "online"} />}
          >
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
              <ChatWindow messages={messages} cards={cards} loading={loading} />
              <ChatInput onSend={handleSend} disabled={loading} />
            </div>
          </Panel>

          <Panel
            icon="brain"
            iconTone="from-slate-950 to-slate-800"
            title="Reasoning engine"
            subtitle="Trace · Evidence · Decisions"
            status={<CodePill label="zoe-core v4.2" />}
          >
            <div className="flex min-h-0 flex-1 flex-col p-5">
              <div className="flex min-h-0 flex-1 flex-col">
                <SectionHeader
                  icon="clipboard"
                  label="Agent Reasoning"
                  value={`${agentReasoningItems.length} insights`}
                />
                <div className="mt-3 flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto overscroll-contain rounded-xl bg-slate-950 px-4 py-4 text-xs leading-5 text-slate-300">
                  {agentReasoningItems.length === 0 ? (
                    <p className="font-mono text-slate-400">Waiting for agent reasoning...</p>
                  ) : (
                    agentReasoningItems.map((item, index) => (
                      <ReasoningItem key={`${item.title}-${index}`} item={item} />
                    ))
                  )}
                  <div ref={reasoningEndRef} />
                </div>
              </div>
            </div>
          </Panel>

          <Panel
            icon="pulse"
            iconTone="from-brand to-blue-600"
            title="ITSM dashboard"
            subtitle="Live ticket · SLA · telemetry"
            status={<StatusPill tone={loading ? "blue" : "slate"} label={loading ? "Active" : "Idle"} />}
          >
            <div className="min-h-0 flex-1 overflow-y-auto p-5">
              <div className="flex flex-col gap-5">
              <MetricBlock
                kicker="Ticket"
                title={ticketTitle(latestTicket)}
                action={<MiniIcon name="ticket" className="h-8 w-8 text-brand" />}
              >
                <div className="mt-6">
                  <div className="mb-2 flex items-center justify-between text-sm text-slate-600">
                    <span>Automation progress</span>
                    <span className="font-mono text-slate-950">{automationProgress}%</span>
                  </div>
                  <Progress value={automationProgress} />
                </div>
              </MetricBlock>

              <div className="grid grid-cols-2 gap-4">
                <SmallMetric
                  kicker="Elapsed"
                  title={messages.length ? `${Math.max(1, messages.length)}m` : "-"}
                  detail={state === "complete" ? "Complete" : "On track"}
                />
                <SmallMetric
                  kicker="SLA window"
                  title={state === "complete" ? "Met" : "-"}
                  progress={state === "complete" ? 100 : automationProgress}
                />
              </div>
              </div>
            </div>
          </Panel>
        </section>
      </div>
    </div>
  );
}

const FALLBACK_WORKFLOWS = [
  { id: "local_system_agent", title: "Local System Agent", active: true },
  { id: "system_slow_diagnostics", title: "System Slow Diagnostics", active: true },
  { id: "new_employee_onboarding", title: "New Employee Onboarding", active: true },
  { id: "windows_update_failure", title: "Windows Update Failure", active: true },
];

function MobileWorkflowLauncher({ onSelect }) {
  const {
    data: workflows = [],
    isError,
    isLoading,
  } = useQuery({
    queryKey: ["workflows"],
    queryFn: listWorkflows,
    staleTime: 5 * 60 * 1000,
  });
  const visibleWorkflows = workflows.length ? workflows : FALLBACK_WORKFLOWS;

  return (
    <section className="mb-4 shrink-0 md:hidden">
      <div className="mb-2 flex items-center justify-between gap-3">
        <p className="font-mono text-xs uppercase tracking-[0.28em] text-slate-600">
          Workflows
        </p>
        {(isLoading || isError || workflows.length === 0) && (
          <span className="shrink-0 text-xs text-slate-500">
            {isLoading
              ? "Loading..."
              : isError
                ? "Using defaults"
                : "Defaults"}
          </span>
        )}
      </div>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {visibleWorkflows.map((workflowItem) => (
          <button
            key={workflowItem.id}
            type="button"
            onClick={() => onSelect(workflowItem.id)}
            className={`shrink-0 rounded-lg border px-3 py-2 text-sm font-medium ${
              workflowItem.active
                ? "border-blue-200 bg-blue-50 text-blue-800"
                : "border-slate-200 bg-white text-slate-500"
            }`}
          >
            {workflowItem.title}
          </button>
        ))}
      </div>
    </section>
  );
}

function Panel({ icon, iconTone, title, subtitle, status, children }) {
  return (
    <article className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border border-slate-100 bg-white shadow-[0_16px_36px_rgba(15,23,42,0.08)]">
      <header className="flex min-h-[76px] shrink-0 items-center justify-between gap-3 border-b border-slate-200 px-5">
        <div className="flex min-w-0 items-center gap-3">
          <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-br ${iconTone} text-white shadow-sm`}>
            <PanelIcon name={icon} />
          </div>
          <div className="min-w-0">
            <h2 className="truncate text-base font-bold text-slate-950">{title}</h2>
            <p className="truncate text-sm text-slate-600">{subtitle}</p>
          </div>
        </div>
        {status}
      </header>
      {children}
    </article>
  );
}

function MetricBlock({ kicker, title, action, children }) {
  return (
    <section className="rounded-xl bg-slate-50 p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="mb-3 font-mono text-xs uppercase tracking-[0.35em] text-slate-700">
            {kicker}
          </p>
          <h3 className="truncate text-xl font-medium text-slate-700">{title}</h3>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

function SmallMetric({ kicker, title, detail, progress }) {
  return (
    <section className="rounded-xl bg-slate-50 p-4">
      <p className="mb-5 font-mono text-xs uppercase tracking-[0.3em] text-slate-700">
        {kicker}
      </p>
      <p className="text-xl font-bold text-slate-950">{title}</p>
      {detail && <p className="mt-3 text-sm font-medium text-emerald-600">{detail}</p>}
      {progress != null && <Progress value={progress} className="mt-6" />}
    </section>
  );
}

function ReasoningItem({ item }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/5 px-3 py-2">
      <div className="flex items-start justify-between gap-3">
        <p className="font-semibold text-white">{item.title}</p>
        {item.meta && (
          <span className="shrink-0 rounded bg-white/10 px-2 py-0.5 font-mono text-[10px] uppercase text-slate-300">
            {item.meta}
          </span>
        )}
      </div>
      {item.detail && <p className="mt-1 text-slate-300">{item.detail}</p>}
    </div>
  );
}

function SectionHeader({ icon, label, value }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-2">
        <MiniIcon name={icon} className="h-4 w-4 text-slate-500" />
        <p className="truncate font-mono text-xs uppercase tracking-[0.35em] text-slate-700">
          {label}
        </p>
      </div>
      <span className="shrink-0 font-mono text-xs text-slate-600">{value}</span>
    </div>
  );
}

function StatusPill({ tone, label }) {
  const tones = {
    emerald: ["bg-emerald-50 text-slate-600", "bg-emerald-500"],
    blue: ["bg-blue-50 text-blue-700", "bg-brand"],
    slate: ["bg-slate-100 text-slate-600", "bg-slate-500"],
  };
  const [pillClass, dotClass] = tones[tone];
  return (
    <span className={`inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm ${pillClass}`}>
      <span className={`h-2.5 w-2.5 rounded-full ${dotClass}`} />
      {label}
    </span>
  );
}

function CodePill({ label }) {
  return (
    <span className="rounded-lg bg-slate-100 px-3 py-2 font-mono text-xs text-slate-700">
      {label}
    </span>
  );
}

function Progress({ value, className = "" }) {
  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white shadow-inner">
        <div
          className="h-full rounded-full bg-brand transition-all"
          style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
        />
      </div>
      <span className="w-8 text-right font-mono text-xs text-slate-950">{value}%</span>
    </div>
  );
}

function PanelIcon({ name }) {
  return <MiniIcon name={name} className="h-5 w-5" />;
}

function MiniIcon({ name, className = "h-4 w-4" }) {
  const paths = {
    spark: (
      <>
        <path d="M12 3l1.7 5.2L19 10l-5.3 1.8L12 17l-1.7-5.2L5 10l5.3-1.8L12 3Z" />
        <path d="M5 3v4M3 5h4" />
      </>
    ),
    brain: <path d="M9 4a3 3 0 0 0-3 3v1a3 3 0 0 0 0 6v1a3 3 0 0 0 5 2.2V6.8A3 3 0 0 0 9 4Zm6 0a3 3 0 0 1 3 3v1a3 3 0 0 1 0 6v1a3 3 0 0 1-5 2.2V6.8A3 3 0 0 1 15 4Z" />,
    pulse: <path d="M3 12h4l2-6 4 12 2-6h6" />,
    shield: <path d="M12 3 6 5v5c0 4 2.5 7 6 9 3.5-2 6-5 6-9V5l-6-2Z" />,
    list: <path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01" />,
    ticket: <path d="M3 8a2 2 0 0 1 2-2h14v4a2 2 0 0 0 0 4v4H5a2 2 0 0 1-2-2v-4a2 2 0 0 0 0-4Z" />,
    clipboard: <path d="M9 4h6l1 2h3v14H5V6h3l1-2ZM9 10h6M9 14h6" />,
  };

  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.8"
      viewBox="0 0 24 24"
    >
      {paths[name]}
    </svg>
  );
}

function getAutomationProgress(state, cards) {
  if (state === "complete") return 100;
  if (cards.some((card) => card.kind === "ticket_draft")) return 75;
  if (cards.some((card) => card.kind === "diagnostic_result")) return 55;
  if (cards.some((card) => card.kind === "diagnostic_status")) return 30;
  return 0;
}

function ticketTitle(card) {
  if (!card) return "-";
  if (card.kind === "ticket_created") return card.data?.ticket_id || "Ticket created";
  return card.data?.title || "Ticket draft ready";
}

function getAgentReasoningItems(cards, latestDiagnostic) {
  const items = [];
  cards.forEach((card) => {
    const data = card.data || {};
    if (card.kind === "diagnostic_status") {
      items.push({
        title: "Started endpoint diagnostics",
        detail: `Collecting ${data.method || "browser and local"} metrics for ${data.device_name || "the endpoint"}.`,
        meta: data.status || "diagnostic",
      });
    }
    if (card.kind === "diagnostic_result") {
      const evidenceLabel = diagnosticEvidenceLabel(data);
      addTextItem(items, "Diagnostic summary", diagnosticSummaryText(data), evidenceLabel);
      addTraceItems(items, data.tool_trace, "Tool");
      items.push({
        title: "Selected diagnostic evidence",
        detail: `The agent used ${evidenceLabel} to normalize device health and decide the next action.`,
        meta: "diagnostic",
      });
    }
    if (card.kind === "onboarding_progress") {
      addTextItem(items, "Onboarding reasoning", data.agent_summary, data.agentic ? "agent" : "fallback");
      addTraceItems(items, data.tool_trace, "Identity");
      (data.steps || []).forEach((step) => {
        items.push({
          title: step.label || "Onboarding step",
          detail: step.detail || "The agent updated this onboarding step.",
          meta: step.status || "step",
        });
      });
    }
    if (card.kind === "workflow") {
      addTextItem(items, "Agent rationale", data.rationale, data.decision || data.step || "workflow");
      addTraceItems(items, data.agent_trace, "Decision");
      if (data.decision || data.selected_check || data.selected_tool) {
        items.push({
          title: workflowDecisionTitle(data),
          detail: workflowDecisionDetail(data),
          meta: data.decision || data.step || "workflow",
        });
      }
      if (data.diagnostic_goal) {
        items.push({
          title: "Local diagnostic goal",
          detail: data.diagnostic_goal,
          meta: data.risk_level || data.status || "plan",
        });
      }
      addListItem(items, "Evidence to collect", data.evidence_to_collect, "evidence");
      addListItem(items, "Success criteria", data.success_criteria, "criteria");
      addTextItem(items, "Command preview", data.command_preview, data.status || "local");
      addTextItem(items, "Local task result", data.summary, data.status);
      addTextItem(items, "Planner issue", data.agent_error, "error");
    }
    if (card.kind === "ticket_draft") {
      items.push({
        title: "Prepared ticket draft",
        detail: `${data.title || "Support ticket"} was drafted from ${latestDiagnostic?.data?.method || "conversation"} evidence with ${data.priority || "medium"} priority.`,
        meta: data.priority || "draft",
      });
    }
    if (card.kind === "ticket_created") {
      items.push({
        title: "Created ITSM ticket",
        detail: `${data.ticket_id || "Ticket"} is now ${data.status || "open"}.`,
        meta: "ticket",
      });
    }
  });
  return compactReasoningItems(items);
}

function addTraceItems(items, trace, label) {
  if (!Array.isArray(trace)) return;
  trace.forEach((event) => {
    const name = event.tool || event.decision || event.step || event.action;
    if (!name) return;
    const resultEvidence = event.result ? diagnosticEvidenceLabel(event.result) : "";
    items.push({
      title: `${label}: ${toTitleCase(name)}`,
      detail:
        traceMethodDetail(event, resultEvidence) ||
        event.rationale ||
        event.message ||
        event.summary ||
        event.status ||
        traceResultSummary(event.result) ||
        "The agent recorded this reasoning step.",
      meta: resultEvidence || event.status || event.source || event.selected_tool || "trace",
    });
  });
}

function addTextItem(items, title, detail, meta) {
  if (!detail) return;
  items.push({
    title,
    detail: truncateText(String(detail), 180),
    meta,
  });
}

function addListItem(items, title, values, meta) {
  if (!Array.isArray(values) || values.length === 0) return;
  items.push({
    title,
    detail: values.slice(0, 3).join(", "),
    meta,
  });
}

function workflowDecisionTitle(data) {
  if (data.selected_tool) return `Selected local tool: ${toTitleCase(data.selected_tool)}`;
  if (data.selected_check) return `Selected check: ${toTitleCase(data.selected_check)}`;
  if (data.decision) return `Decision: ${toTitleCase(data.decision)}`;
  return toTitleCase(data.step || "Workflow decision");
}

function workflowDecisionDetail(data) {
  if (data.rationale) return truncateText(data.rationale, 180);
  if (data.message) return truncateText(data.message, 180);
  if (data.selected_tool) return "The agent chose an allowlisted local action after evaluating the workflow state.";
  if (data.selected_check) return "The agent chose the next user-facing troubleshooting check.";
  return data.summary || "The workflow state was updated from the latest agent decision.";
}

function traceResultSummary(result) {
  if (!result || typeof result !== "object") return "";
  if (result.summary) return result.summary;
  if (result.recommendation) return result.recommendation;
  if (result.title) return result.title;
  if (result.method) return `Collected ${result.method} evidence.`;
  return "";
}

function diagnosticSummaryText(data) {
  const metrics = diagnosticMetrics(data);
  if (metrics.local_app_available) {
    return (
      data.summary ||
      metrics.local_app_summary ||
      metrics.diagnostic_recommendation ||
      "Browser diagnostics were enriched with local app telemetry."
    );
  }
  return data.agent_summary || data.summary;
}

function diagnosticEvidenceLabel(data) {
  const metrics = diagnosticMetrics(data);
  if (metrics.local_app_available || metrics.local_app_response) {
    return "local app telemetry";
  }
  if (data.method === "browser_only") return "browser-only evidence";
  return data.method || "diagnostic evidence";
}

function diagnosticMetrics(data = {}) {
  return data.metrics || data.result || data;
}

function traceMethodDetail(event, resultEvidence) {
  if (event.tool === "select_diagnostic_method" && event.method === "browser_only") {
    return "Selected the browser fallback adapter; local app telemetry is applied when the submitted browser payload includes it.";
  }
  if (event.method === "browser_only" && resultEvidence === "local app telemetry") {
    return "Collected browser-submitted diagnostics enriched by the local app server.";
  }
  return "";
}

function compactReasoningItems(items) {
  const seen = new Set();
  return items
    .map((item) => ({
      ...item,
      title: truncateText(item.title, 72),
      detail: truncateText(item.detail, 180),
      meta: truncateText(item.meta || "", 22),
    }))
    .filter((item) => {
      const key = `${item.title}|${item.detail}|${item.meta}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function truncateText(value, maxLength) {
  const text = String(value || "").trim();
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 1).trim()}...`;
}

function toTitleCase(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

async function maybeAutoSubmitBrowserDiagnostics(
  resp,
  sessionId,
  addAssistantResponse,
) {
  if (!resp?.metadata?.trigger_browser_diagnostics) return;
  try {
    const diagnosticCard = resp.cards?.find(
      (card) => card.kind === "diagnostic_status",
    );
    const payload = await collectBrowserDiagnostics({
      sessionId,
      deviceName: diagnosticCard?.data?.device_name,
      diagnosticId: diagnosticCard?.data?.diagnostic_id,
    });
    await submitBrowserDiagnostics(sessionId, payload);
    // Nudge backend to continue the workflow with the freshly-uploaded data.
    const next = await sendAgentMessage(sessionId, "browser diagnostics ready");
    addAssistantResponse(next);
  } catch (_) {
    // Non-fatal — backend will simply have empty browser metrics.
  }
}

async function maybeAutoExecuteLocalAppAction(
  resp,
  sessionId,
  addAssistantResponse,
  setPendingLocalAction,
) {
  let current = resp;
  const seenActions = new Set();

  for (let attempt = 0; attempt < 3; attempt += 1) {
    const actionRequest = current?.metadata?.trigger_local_app_action;
    if (!actionRequest?.action) return;

    if (actionRequest.requires_confirmation) {
      setPendingLocalAction(actionRequest);
      return;
    }

    const actionKey = `${actionRequest.action}:${actionRequest.device_name || ""}`;
    if (seenActions.has(actionKey)) return;
    seenActions.add(actionKey);

    current = await executeAndSubmitLocalAction(
      actionRequest,
      sessionId,
      addAssistantResponse,
    );
  }
}

async function executeAndSubmitLocalAction(
  actionRequest,
  sessionId,
  addAssistantResponse,
) {
  try {
    const result = await executeLocalAppAction(actionRequest.action, {
      sessionId,
      deviceName: actionRequest.device_name,
      diagnosticId: actionRequest.diagnostic_id,
      taskId: actionRequest.task_id,
      command: actionRequest.command,
      timeoutSeconds: actionRequest.timeout_seconds,
    });
    await submitLocalActionResult(sessionId, {
      ...result,
      task_context: buildTaskContext(actionRequest),
    });
    const current = await sendAgentMessage(sessionId, "local app action complete");
    addAssistantResponse(current);
    return current;
  } catch (error) {
    await submitLocalActionResult(sessionId, {
      action: actionRequest.action,
      task_id: actionRequest.task_id,
      status: "failed",
      message:
        "Unable to contact the local app diagnostic server at http://127.0.0.1:8765/local-app.",
      stopped_processes: [],
      service_statuses: {},
      pending_reboot: null,
      errors: [error?.message || "local_app_unreachable"],
      task_context: buildTaskContext(actionRequest),
    });
    const current = await sendAgentMessage(sessionId, "local app action failed");
    addAssistantResponse(current);
    return current;
  }
}

function confirmationMessage(actionRequest) {
  if (!actionRequest) return "";
  const commandNotice = actionRequest.command
    ? "\n\nCommand: shown below for review."
    : "";
  const risk = actionRequest.risk_level
    ? `\n\nRisk: ${actionRequest.risk_level}`
    : "";
  return `${actionRequest.summary || "Run a local system action?"}${risk}${commandNotice}`;
}

function buildTaskContext(actionRequest = {}) {
  return {
    task_id: actionRequest.task_id,
    action: actionRequest.action,
    user_request: actionRequest.user_request,
    summary: actionRequest.summary,
    command: actionRequest.command,
    risk_level: actionRequest.risk_level,
    timeout_seconds: actionRequest.timeout_seconds,
    expected_result: actionRequest.expected_result,
    interpretation_hint: actionRequest.interpretation_hint,
    diagnostic_goal: actionRequest.diagnostic_goal,
    evidence_to_collect: actionRequest.evidence_to_collect,
    success_criteria: actionRequest.success_criteria,
    limitations: actionRequest.limitations,
    output_schema_hint: actionRequest.output_schema_hint,
  };
}

function formatAssistantError(error, actionLabel) {
  const status = error?.response?.status;
  const serverMessage =
    error?.response?.data?.detail ||
    error?.response?.data?.message ||
    error?.message ||
    "Unknown error";

  if (!error?.response) {
    return (
      `Unable to reach the backend while ${actionLabel}. ` +
      `Backend URL: ${API_BASE_URL}. Reason: ${serverMessage}. ` +
      `If you are using a LAN address, start the backend with --host 0.0.0.0, ` +
      `or use ${API_LOCAL_FALLBACK_URL} on this machine.`
    );
  }

  return (
    `The backend returned an error while ${actionLabel}. ` +
    `Backend URL: ${API_BASE_URL}. Status: ${status}. Reason: ${serverMessage}.`
  );
}
