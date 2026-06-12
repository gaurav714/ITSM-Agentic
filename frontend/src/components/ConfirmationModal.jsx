export default function ConfirmationModal({
  open,
  title,
  message,
  highlightMessage,
  detailLabel,
  detailText,
  onConfirm,
  onCancel,
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl bg-white shadow-lg">
        <div className="shrink-0 border-b border-slate-200 px-5 py-4">
          <h3 className="text-base font-semibold text-slate-900">{title}</h3>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {highlightMessage && (
            <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950">
              <p className="font-bold">Permission required</p>
              <p className="mt-1">{highlightMessage}</p>
            </div>
          )}
          <p className="whitespace-pre-wrap text-sm text-slate-600">{message}</p>
          {detailText && (
            <div className="mt-4">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                {detailLabel || "Details"}
              </p>
              <pre className="max-h-72 overflow-auto rounded-lg border border-slate-200 bg-slate-950 p-3 font-mono text-xs leading-5 text-slate-100">
                {detailText}
              </pre>
            </div>
          )}
        </div>
        <div className="shrink-0 border-t border-slate-200 px-5 py-4 flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="rounded-md border border-slate-300 px-4 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="rounded-md bg-brand px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-dark"
          >
            Confirm
          </button>
        </div>
      </div>
    </div>
  );
}
