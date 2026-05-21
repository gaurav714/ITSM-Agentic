const LOCAL_APP_URL =
  import.meta.env.VITE_LOCAL_APP_URL || "http://127.0.0.1:8765/local-app";

/**
 * Browser-side diagnostics. The browser first gathers its own limited metrics,
 * then optionally calls a local app diagnostic server for richer tool data.
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
    browser_hardware_concurrency: navigator.hardwareConcurrency || null,
    device_memory_gb: navigator.deviceMemory || null,
    online: navigator.onLine,
    connection_type: navConn.effectiveType || null,
    page_load_ms: pageLoadMs,
    extra: {
      language: navigator.language,
      screen: { w: window.screen?.width, h: window.screen?.height },
    },
  };

  const localApp = await queryLocalApp(browserMetrics, context);

  return {
    ...browserMetrics,
    local_app_available: Boolean(localApp.response),
    local_app_response: localApp.response,
    local_app_error: localApp.error,
  };
}

export async function executeLocalAppAction(action, context = {}) {
  const toolsByAction = {
    stop_edge: "actions.stop_edge",
    open_windows_update_settings: "actions.open_windows_update_settings",
    collect_windows_update_status: "actions.collect_windows_update_status",
  };
  const toolName = toolsByAction[action];

  if (!toolName) {
    return {
      action,
      status: "rejected",
      message: "This local app action is not supported by the browser client.",
      stopped_processes: [],
      errors: [],
    };
  }

  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 5000);

  try {
    return await callLocalAppTool(
      toolName,
      {
        action,
        context: {
          session_id: context.sessionId,
          device_name: context.deviceName,
          diagnostic_id: context.diagnosticId,
        },
      },
      controller.signal,
    );
  } finally {
    window.clearTimeout(timeout);
  }
}

async function queryLocalApp(browserMetrics, context) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 2500);

  try {
    const response = await callLocalAppTool(
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
    return { response: null, error: `local_app_${name}` };
  } finally {
    window.clearTimeout(timeout);
  }
}

async function callLocalAppTool(name, args, signal) {
  const response = await fetch(LOCAL_APP_URL, {
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
    throw new Error(`local_app_http_${response.status}`);
  }

  const payload = await response.json();
  if (payload.error) {
    throw new Error(payload.error.message || "local_app_error");
  }

  return payload.result?.structuredContent || {};
}
