const LOCAL_DIAGNOSTIC_AGENT_URL = normalizeLocalMcpUrl(
  import.meta.env.VITE_LOCAL_DIAGNOSTIC_AGENT_URL ||
    "http://127.0.0.1:8765/mcp",
);

/**
 * Browser-side diagnostics. The browser first gathers its own limited metrics,
 * then optionally calls a local MCP diagnostic server for richer tool data.
 * The backend receives the combined payload.
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

  return callLocalMcpTool("actions.stop_edge", {
    action,
    context: {
      session_id: context.sessionId,
      device_name: context.deviceName,
      diagnostic_id: context.diagnosticId,
    },
  });
}

async function queryLocalDiagnosticAgent(browserMetrics, context) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 2500);

  try {
    const response = await callLocalMcpTool(
      "diagnostics.search",
      {
        query: "system is slow",
        context: {
          session_id: context.sessionId,
          device_name: context.deviceName,
          diagnostic_id: context.diagnosticId,
          browser_metrics: browserMetrics,
        },
      },
      controller.signal,
    );

    return { response, error: null };
  } catch (error) {
    const name = error?.name === "AbortError" ? "timeout" : "unreachable";
    return { response: null, error: `local_agent_${name}` };
  } finally {
    window.clearTimeout(timeout);
  }
}

async function callLocalMcpTool(name, args, signal) {
  const response = await fetch(LOCAL_DIAGNOSTIC_AGENT_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    signal,
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      method: "tools/call",
      params: { name, arguments: args },
    }),
  });

  if (!response.ok) {
    throw new Error(`local_mcp_http_${response.status}`);
  }

  const payload = await response.json();
  if (payload.error) {
    throw new Error(payload.error.message || "local_mcp_error");
  }

  return payload.result?.structuredContent || {};
}

function normalizeLocalMcpUrl(url) {
  return String(url)
    .replace(/\/diagnostics\/search$/, "/mcp")
    .replace(/\/actions\/stop-edge$/, "/mcp");
}
