export default function OnboardingProgressCard({ data }) {
  const employee = data.employee || {};
  const steps = data.steps || [];

  return (
    <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-semibold text-emerald-950">
            New employee onboarding
          </h4>
          <p className="mt-1 text-sm font-medium text-slate-800">
            {employee.full_name || "Employee"}
          </p>
          <p className="text-xs text-slate-600">
            {[employee.email, employee.department, employee.role]
              .filter(Boolean)
              .join(" / ")}
          </p>
        </div>
        {data.onboarding_id && (
          <span className="rounded bg-white px-2 py-0.5 text-[10px] font-medium text-emerald-800 ring-1 ring-emerald-200">
            {data.onboarding_id}
          </span>
        )}
        {data.tool_trace?.length > 0 && !data.onboarding_id && (
          <span className="rounded bg-white px-2 py-0.5 text-[10px] font-medium text-emerald-800 ring-1 ring-emerald-200">
            {data.agentic ? "LLM agent" : "Tool fallback"}
          </span>
        )}
      </div>

      <ol className="mt-4 space-y-2">
        {steps.map((step) => (
          <li key={step.label} className="flex gap-3 rounded bg-white p-3">
            <span
              className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${
                step.status === "complete"
                  ? "bg-emerald-600 text-white"
                  : "bg-slate-200 text-slate-600"
              }`}
            >
              {step.status === "complete"
                ? "OK"
                : step.status === "skipped"
                  ? "SKIP"
                  : "..."}
            </span>
            <div>
              <p className="text-xs font-semibold text-slate-800">
                {step.label}
              </p>
              <p className="mt-0.5 text-xs text-slate-600">{step.detail}</p>
            </div>
          </li>
        ))}
      </ol>

      {data.groups?.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {data.groups.map((group) => (
            <span
              key={group}
              className="rounded bg-white px-2 py-0.5 text-[11px] text-slate-700 ring-1 ring-emerald-100"
            >
              {group}
            </span>
          ))}
        </div>
      )}

      {data.tool_trace?.length > 0 && (
        <div className="mt-3 rounded bg-white p-3 ring-1 ring-emerald-100">
          <p className="text-[11px] font-semibold uppercase text-emerald-900">
            Agent tool trace
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {data.tool_trace.map((event, index) => (
              <span
                key={`${event.tool}-${index}`}
                className="rounded px-2 py-0.5 text-[11px] text-slate-700 ring-1 ring-slate-200"
              >
                {event.tool}: {event.status}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
