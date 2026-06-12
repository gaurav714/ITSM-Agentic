import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { listWorkflows } from "../api/agentApi.js";

const FALLBACK_WORKFLOWS = [
  { id: "local_system_agent", title: "Local System Agent", active: true },
  { id: "system_slow_diagnostics", title: "System Slow Diagnostics", active: true },
  { id: "new_employee_onboarding", title: "New Employee Onboarding", active: true },
  { id: "windows_update_failure", title: "Windows Update Failure", active: true },
];

export default function Sidebar() {
  const navigate = useNavigate();
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
    <aside className="hidden w-64 shrink-0 border-r border-slate-200 bg-white p-4 md:block">
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
        Workflows
      </h2>
      {isLoading && (
        <p className="mb-3 rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-500">
          Loading workflows...
        </p>
      )}
      {isError && (
        <p className="mb-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          Unable to load workflows. Showing defaults.
        </p>
      )}
      {!isLoading && !isError && workflows.length === 0 && (
        <p className="mb-3 rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-500">
          No workflows returned. Showing defaults.
        </p>
      )}
      <ul className="space-y-1">
        {visibleWorkflows.map((w) => (
          <li key={w.id}>
            <button
              onClick={() => navigate(`/chat/${w.id}`)}
              className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm transition ${
                w.active
                  ? "text-slate-800 hover:bg-brand/10 hover:text-brand"
                  : "text-slate-400 hover:bg-slate-50"
              }`}
            >
              <span>{w.title}</span>
              {!w.active && (
                <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500">
                  Soon
                </span>
              )}
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
