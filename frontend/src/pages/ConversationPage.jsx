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
  executeLocalAgentAction,
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
        await maybeAutoExecuteLocalAgentAction(
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
      await maybeAutoExecuteLocalAgentAction(
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

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-slate-200 bg-white px-6 py-3">
        <h2 className="text-sm font-semibold text-slate-800">
          {workflow ? workflow.replaceAll("_", " ") : "AI Helpdesk Chat"}
        </h2>
        <p className="text-xs text-slate-500">
          Session: {sessionId.slice(0, 8)} • State: {state}
        </p>
      </div>
      <ChatWindow messages={messages} cards={cards} loading={loading} />
      <ChatInput onSend={handleSend} disabled={loading} />
    </div>
  );
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

async function maybeAutoExecuteLocalAgentAction(
  resp,
  sessionId,
  addAssistantResponse,
) {
  const actionRequest = resp?.metadata?.trigger_local_agent_action;
  if (!actionRequest?.action) return;

  try {
    const result = await executeLocalAgentAction(actionRequest.action, {
      sessionId,
      deviceName: actionRequest.device_name,
      diagnosticId: actionRequest.diagnostic_id,
    });
    await submitLocalActionResult(sessionId, result);
    const next = await sendAgentMessage(sessionId, "local action complete");
    addAssistantResponse(next);
  } catch (error) {
    await submitLocalActionResult(sessionId, {
      action: actionRequest.action,
      status: "failed",
      message: "Unable to contact the local MCP diagnostic server.",
      stopped_processes: [],
      errors: [error?.message || "local_agent_unreachable"],
    });
    const next = await sendAgentMessage(sessionId, "local action failed");
    addAssistantResponse(next);
  }
}
