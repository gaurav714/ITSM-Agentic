export default function TicketDraftCard({ data }) {
  return (
    <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 shadow-sm">
      <div className="mb-1 flex items-center justify-between">
        <h4 className="text-sm font-semibold text-blue-900">Ticket draft</h4>
        <span className="rounded bg-white px-2 py-0.5 text-[10px] font-medium text-blue-800 ring-1 ring-blue-200">
          {data.priority}
        </span>
      </div>
      <p className="text-sm font-medium text-slate-800">{data.title}</p>
      <p className="mt-2 whitespace-pre-wrap text-xs text-slate-700">
        {data.description}
      </p>
      <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-slate-600">
        <Tag>{data.category}</Tag>
        {data.device_name && <Tag>Device: {data.device_name}</Tag>}
      </div>
      <p className="mt-3 text-[11px] italic text-blue-800">
        Reply 'yes' to create this ticket or 'no' to cancel.
      </p>
    </div>
  );
}

function Tag({ children }) {
  return (
    <span className="rounded bg-white px-2 py-0.5 ring-1 ring-slate-200">
      {children}
    </span>
  );
}
