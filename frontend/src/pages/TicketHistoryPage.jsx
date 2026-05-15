import { useQuery } from "@tanstack/react-query";
import { listTickets } from "../api/ticketApi.js";

export default function TicketHistoryPage() {
  const { data: tickets = [], isLoading } = useQuery({
    queryKey: ["tickets"],
    queryFn: listTickets,
    refetchInterval: 5000,
  });

  return (
    <div className="h-full overflow-y-auto p-8">
      <div className="mx-auto max-w-4xl">
        <h1 className="text-2xl font-semibold text-slate-900">
          Ticket history
        </h1>
        {isLoading && <p className="mt-3 text-sm text-slate-500">Loading…</p>}
        {!isLoading && tickets.length === 0 && (
          <p className="mt-3 text-sm text-slate-500">No tickets yet.</p>
        )}
        <ul className="mt-4 space-y-3">
          {tickets.map((t) => (
            <li
              key={t.ticket_id}
              className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-sm font-semibold text-slate-800">
                  {t.ticket_id}
                </span>
                <span className="rounded bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700 ring-1 ring-emerald-200">
                  {t.status}
                </span>
              </div>
              <p className="mt-1 text-sm font-medium text-slate-800">
                {t.title}
              </p>
              <p className="mt-1 whitespace-pre-wrap text-xs text-slate-600">
                {t.description}
              </p>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
