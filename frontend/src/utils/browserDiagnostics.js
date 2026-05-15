const LOCAL_DIAGNOSTIC_AGENT_URL =
  import.meta.env.VITE_LOCAL_DIAGNOSTIC_AGENT_URL ||
  "http://127.0.0.1:8765/diagnostics/search";
const LOCAL_DIAGNOSTIC_AGENT_STOP_EDGE_URL =
  import.meta.env.VITE_LOCAL_DIAGNOSTIC_AGENT_STOP_EDGE_URL ||
  LOCAL_DIAGNOSTIC_AGENT_URL.replace(
    /\/diagnostics\/search$/,
    "/actions/stop-edge",
  );

/**
 * Browser-side diagnostics. The browser first gathers its own limited metrics,
 * then optionally asks a local user-system diagnostic agent for richer tool
 * search/diagnostic data. The backend receives the combined payload.
 */
export async function collectBrowserDiagnostics(context = {}) {
  const navConn = navigator.connection || {};
  let pageLoadMs = null;
  try {
    const [nav] = performance.getEntriesByType("navigation");
    if (nav) pageLoadMs = nav.duration;
  } catch (_) {
    /* ignore */
  }

  const browserMetrics = {
    user_agent: navigator.userAgent,
    platform: navigator.platform,
    cpu_cores: navigator.hardwareConcurrency || null,
    device_memory_gb: navigator.deviceMemory || null,
    online: navigator.onLine,
    connection_type: navConn.effectiveType || null,
    page_load_ms: pageLoadMs,
    extra: {
      language: navigator.language,
      screen: { w: window.screen?.width, h: window.screen?.height },
    },
  };

  const localAgent = await queryLocalDiagnosticAgent(browserMetrics, context);

  return {
    ...browserMetrics,
    local_agent_available: Boolean(localAgent.response),
    local_agent_response: localAgent.response,
    local_agent_error: localAgent.error,
  };
}

export async function executeLocalAgentAction(action, context = {}) {
  if (action !== "stop_edge") {
    return {
      action,
      status: "rejected",
      message: "This local action is not supported by the browser client.",
      stopped_processes: [],
      errors: [],
    };
  }

  const response = await fetch(LOCAL_DIAGNOSTIC_AGENT_STOP_EDGE_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action,
      context: {
        session_id: context.sessionId,
        device_name: context.deviceName,
        diagnostic_id: context.diagnosticId,
      },
    }),
  });

  if (!response.ok) {
    return {
      action,
      status: "failed",
      message: `Local diagnostic assistant returned HTTP ${response.status}.`,
      stopped_processes: [],
      errors: [`http_${response.status}`],
    };
  }

  return response.json();
}

async function queryLocalDiagnosticAgent(browserMetrics, context) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 2500);

  try {
    const response = await fetch(LOCAL_DIAGNOSTIC_AGENT_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      body: JSON.stringify({
        query: "system is slow",
        context: {
          session_id: context.sessionId,
          device_name: context.deviceName,
          diagnostic_id: context.diagnosticId,
          browser_metrics: browserMetrics,
        },
      }),
    });

    if (!response.ok) {
      return { response: null, error: `local_agent_http_${response.status}` };
    }

    return { response: await response.json(), error: null };
  } catch (error) {
    const name = error?.name === "AbortError" ? "timeout" : "unreachable";
    return { response: null, error: `local_agent_${name}` };
  } finally {
    window.clearTimeout(timeout);
  }
}
