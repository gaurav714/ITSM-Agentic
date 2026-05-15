import { useEffect, useRef } from "react";
import { useParams } from "react-router-dom";
import ChatWindow from "../components/ChatWindow.jsx";
import ChatInput from "../components/ChatInput.jsx";
import { useConversationStore } from "../store/useConversationStore.js";
import { sendAgentMessage, startWorkflow } from "../api/agentApi.js";
import {
  submitBrowserDiagnostics,
  submitLocalActionResult,
} from "../api/diagnosticApi.js";
import {
  collectBrowserDiagnostics,
  executeLocalMcpAction,
} from "../utils/browserDiagnostics.js";

export default function ConversationPage() {
  const { workflowId } = useParams();
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
        await maybeAutoExecuteLocalMcpAction(
          resp,
          sessionId,
          addAssistantResponse,
        );
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
      await maybeAutoExecuteLocalMcpAction(
        resp,
        sessionId,
        addAssistantResponse,
      );
    } catch (e) {
      addAssistantResponse({
        message:
          "Sorry, something went wrong contacting the assistant. Please try again.",
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
  const intentLabel = workflow
    ? workflow.replaceAll("_", " ")
    : messages.length
      ? "General IT support"
      : "Awaiting first message...";
  const confidence = messages.length ? Math.min(96, 42 + messages.length * 13) : 0;
  const workflowLabel = workflow ? workflow.replaceAll("_", " ") : "Password Reset";

  return (
    <div className="h-full overflow-hidden bg-white">
      <div className="mx-auto flex h-full w-full max-w-[1440px] flex-col px-4 pb-5 sm:px-6 lg:px-[60px]">
        <section className="mb-5 shrink-0 rounded-b-xl bg-slate-100 px-6 py-3 text-slate-800">
          <p className="text-base leading-7">
            Fully automated ITSM assistance with diagnostics, ticket drafting,
            and live workflow telemetry in one operational console.
          </p>
        </section>

        <section className="grid min-h-0 flex-1 gap-4 overflow-hidden lg:grid-cols-[1.05fr_1.05fr_1fr]">
          <Panel
            icon="spark"
            iconTone="from-indigo-500 to-brand"
            title="Zoe · IT Assistant"
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
            subtitle="Intent · Classification · Actions"
            status={<CodePill label="zoe-core v4.2" />}
          >
            <div className="min-h-0 flex-1 overflow-y-auto p-5">
              <div className="flex flex-col gap-5">
              <MetricBlock kicker="Intent" title={toTitleCase(intentLabel)}>
                <div className="mt-5 grid grid-cols-2 gap-5 text-sm">
                  <div>
                    <p className="text-slate-600">Classification</p>
                    <span className="mt-2 inline-flex items-center gap-1 rounded-lg bg-white px-2 py-1 text-xs font-semibold text-slate-950 shadow-sm ring-1 ring-slate-100">
                      <MiniIcon name="shield" />
                      L1
                    </span>
                  </div>
                  <div>
                    <p className="text-slate-600">Confidence</p>
                    <Progress value={confidence} className="mt-3" />
                  </div>
                </div>
              </MetricBlock>

              <MetricBlock kicker="Next action" title={toTitleCase(nextActionForState(state, loading))} />

              <div>
                <SectionHeader
                  icon="list"
                  label="Automated actions"
                  value={`${cards.length} events`}
                />
                <div className="mt-3 border-l border-slate-200 pl-4 text-sm leading-6 text-slate-600">
                  {cards.length === 0
                    ? "Actions will stream here as Zoe executes her runbook."
                    : cards.slice(-5).map((card) => (
                        <p key={`${card.kind}-${card.ts}`}>
                          {describeCardEvent(card)}
                        </p>
                      ))}
                </div>
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

              <div>
                <SectionHeader
                  icon="clipboard"
                  label="Automation logs"
                  value={`${cards.length} entries`}
                />
                <div className="mt-3 rounded-xl bg-slate-950 px-4 py-4 font-mono text-xs leading-6 text-slate-300">
                  {cards.length === 0 ? (
                    <p>waiting for events...</p>
                  ) : (
                    cards.slice(-4).map((card) => (
                      <p key={`${card.kind}-log-${card.ts}`}>
                        {formatLogLine(card, latestDiagnostic)}
                      </p>
                    ))
                  )}
                </div>
              </div>
              </div>
            </div>
          </Panel>
        </section>
      </div>
    </div>
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

function nextActionForState(state, loading) {
  if (loading) return "Processing";
  const labels = {
    idle: "Idle",
    awaiting_browser_diagnostics: "Collect diagnostics",
    awaiting_remediation_confirmation: "Confirm remediation",
    awaiting_remediation_action: "Run local action",
    awaiting_confirmation: "Awaiting approval",
    complete: "Complete",
  };
  return labels[state] || state || "Idle";
}

function ticketTitle(card) {
  if (!card) return "-";
  if (card.kind === "ticket_created") return card.data?.ticket_id || "Ticket created";
  return card.data?.title || "Ticket draft ready";
}

function describeCardEvent(card) {
  const names = {
    diagnostic_status: "Started endpoint diagnostic collection.",
    diagnostic_result: "Normalized diagnostic results and generated summary.",
    ticket_draft: "Prepared ITSM ticket draft for review.",
    onboarding_progress: "Updated onboarding automation progress.",
    ticket_created: `Created ticket ${card.data?.ticket_id || ""}.`,
  };
  return names[card.kind] || `Received ${card.kind}.`;
}

function formatLogLine(card, latestDiagnostic) {
  if (card.kind === "diagnostic_result") {
    return `diag:${card.data?.diagnostic_id || "latest"} method=${card.data?.method || "unknown"}`;
  }
  if (card.kind === "ticket_created") {
    return `itsm:create status=${card.data?.status || "created"} id=${card.data?.ticket_id || "-"}`;
  }
  if (card.kind === "ticket_draft") {
    return `itsm:draft priority=${card.data?.priority || "P3"} source=${latestDiagnostic?.data?.method || "chat"}`;
  }
  return `event:${card.kind} ok`;
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

async function maybeAutoExecuteLocalMcpAction(
  resp,
  sessionId,
  addAssistantResponse,
) {
  const actionRequest = resp?.metadata?.trigger_local_mcp_action;
  if (!actionRequest?.action) return;

  try {
    const result = await executeLocalMcpAction(actionRequest.action, {
      sessionId,
      deviceName: actionRequest.device_name,
      diagnosticId: actionRequest.diagnostic_id,
    });
    await submitLocalActionResult(sessionId, result);
    const next = await sendAgentMessage(sessionId, "local MCP action complete");
    addAssistantResponse(next);
  } catch (error) {
    await submitLocalActionResult(sessionId, {
      action: actionRequest.action,
      status: "failed",
      message: "Unable to contact the local MCP diagnostic server.",
      stopped_processes: [],
      errors: [error?.message || "local_mcp_unreachable"],
    });
    const next = await sendAgentMessage(sessionId, "local MCP action failed");
    addAssistantResponse(next);
  }
}
