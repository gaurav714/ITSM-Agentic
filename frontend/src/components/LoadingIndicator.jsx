export default function LoadingIndicator({ label = "Thinking…" }) {
  return (
    <div className="flex items-center gap-2 text-sm text-slate-500">
      <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-brand" />
      <span>{label}</span>
    </div>
  );
}
