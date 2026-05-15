export default function DiagnosticStatusCard({ data }) {
  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 shadow-sm">
      <h4 className="text-sm font-semibold text-amber-900">
        Diagnostics in progress
      </h4>
      <dl className="mt-2 space-y-1 text-xs text-amber-800">
        <div>
          <dt className="inline font-medium">Device:</dt>{" "}
          <dd className="inline">{data.device_name}</dd>
        </div>
        <div>
          <dt className="inline font-medium">Method:</dt>{" "}
          <dd className="inline">{data.method}</dd>
        </div>
        <div>
          <dt className="inline font-medium">Status:</dt>{" "}
          <dd className="inline">{data.status}</dd>
        </div>
      </dl>
    </div>
  );
}
