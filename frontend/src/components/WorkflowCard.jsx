export default function WorkflowCard({ title, description, active, onClick }) {
  return (
    <button
      onClick={onClick}
      disabled={!active}
      className={`flex w-full flex-col items-start rounded-xl border bg-white p-4 text-left shadow-sm transition ${
        active
          ? "border-slate-200 hover:-translate-y-0.5 hover:border-brand hover:shadow-md"
          : "cursor-not-allowed border-slate-100 opacity-60"
      }`}
    >
      <div className="flex w-full items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
        {!active && (
          <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-medium uppercase text-slate-500">
            Coming soon
          </span>
        )}
      </div>
      {description && (
        <p className="mt-1 text-xs text-slate-500">{description}</p>
      )}
    </button>
  );
}
