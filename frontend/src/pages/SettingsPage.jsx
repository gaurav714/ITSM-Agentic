export default function SettingsPage() {
  return (
    <div className="h-full overflow-y-auto p-8">
      <div className="mx-auto max-w-2xl">
        <h1 className="text-2xl font-semibold text-slate-900">Settings</h1>
        <p className="mt-2 text-sm text-slate-600">
          Backend URL is configured via the{" "}
          <code className="rounded bg-slate-100 px-1">VITE_API_BASE_URL</code>{" "}
          environment variable.
        </p>
        <p className="mt-2 text-sm text-slate-600">
          To enable LLM-based intent classification, set{" "}
          <code className="rounded bg-slate-100 px-1">OPENAI_API_KEY</code> on
          the backend.
        </p>
      </div>
    </div>
  );
}
