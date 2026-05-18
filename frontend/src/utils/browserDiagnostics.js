/**
 * Browser-side diagnostics. The browser gathers metrics only it can see; the
 * backend enriches this payload with backend-local diagnostic tools.
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

  return {
    device_name: context.deviceName,
    diagnostic_id: context.diagnosticId,
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
}
