export default function DiagnosticResultCard({ data }) {
  const m = data.metrics || {};
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-2 flex items-center justify-between">
        <h4 className="text-sm font-semibold text-slate-800">
          Diagnostic results
        </h4>
        <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-medium uppercase text-slate-600">
          {data.method}
        </span>
      </div>
      <p className="text-xs text-slate-500">Device: {data.device_name}</p>
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <Metric label="CPU" value={m.cpu_pct != null ? `${m.cpu_pct}%` : "—"} />
        <Metric
          label="Memory"
          value={m.memory_pct != null ? `${m.memory_pct}%` : "—"}
        />
        <Metric
          label="Disk free"
          value={m.disk_free_gb != null ? `${m.disk_free_gb} GB` : "—"}
        />
        <Metric
          label="Physical cores"
          value={m.physical_cpu_cores ?? m.cpu_cores ?? "-"}
        />
        <Metric
          label="Logical processors"
          value={m.logical_cpu_processors ?? "-"}
        />
      </div>
      {!m.physical_cpu_cores && m.browser_reported_cpu_cores && (
        <p className="mt-2 text-[11px] text-slate-500">
          Browser-reported CPU cores: {m.browser_reported_cpu_cores}
        </p>
      )}
      {Array.isArray(m.top_processes) && m.top_processes.length > 0 && (
        <div className="mt-3">
          <p className="text-[11px] font-medium text-slate-500 uppercase">
            Top processes
          </p>
          <ul className="mt-1 list-disc pl-4 text-xs text-slate-700">
            {m.top_processes.slice(0, 5).map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </div>
      )}
      {m.backend_local_available && (
        <div className="mt-3 rounded bg-emerald-50 p-2 text-xs text-emerald-900">
          <p className="font-medium">Backend-local diagnostics responded</p>
          {m.backend_local_summary && (
            <p className="mt-1">{m.backend_local_summary}</p>
          )}
          {m.diagnostic_recommendation && (
            <p className="mt-1">Recommendation: {m.diagnostic_recommendation}</p>
          )}
          {Array.isArray(m.tool_candidates) && m.tool_candidates.length > 0 && (
            <p className="mt-1">
              Tools:{" "}
              {m.tool_candidates
                .map((tool) => tool.name || tool.id || tool)
                .slice(0, 4)
                .join(", ")}
            </p>
          )}
        </div>
      )}
      {!m.backend_local_available && m.backend_local_error && (
        <p className="mt-3 rounded bg-slate-50 p-2 text-xs text-slate-500">
          Backend-local diagnostics: {m.backend_local_error}
        </p>
      )}
      {data.summary && (
        <p className="mt-3 rounded bg-slate-50 p-2 text-xs text-slate-700">
          {data.summary}
        </p>
      )}
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div className="rounded bg-slate-50 p-2">
      <p className="text-[10px] uppercase text-slate-500">{label}</p>
      <p className="text-sm font-semibold text-slate-800">{value}</p>
    </div>
  );
}
