import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { listWorkflows } from "../api/agentApi.js";

export default function Sidebar() {
  const navigate = useNavigate();
  const { data: workflows = [] } = useQuery({
    queryKey: ["workflows"],
    queryFn: listWorkflows,
    staleTime: 5 * 60 * 1000,
  });

  return (
    <aside className="hidden w-64 shrink-0 border-r border-slate-200 bg-white p-4 md:block">
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
        Workflows
      </h2>
      <ul className="space-y-1">
        {workflows.map((w) => (
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
