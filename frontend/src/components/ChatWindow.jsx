import { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble.jsx";
import DiagnosticStatusCard from "./DiagnosticStatusCard.jsx";
import DiagnosticResultCard from "./DiagnosticResultCard.jsx";
import TicketDraftCard from "./TicketDraftCard.jsx";
import OnboardingProgressCard from "./OnboardingProgressCard.jsx";
import LoadingIndicator from "./LoadingIndicator.jsx";

const CARD_RENDERERS = {
  diagnostic_status: DiagnosticStatusCard,
  diagnostic_result: DiagnosticResultCard,
  ticket_draft: TicketDraftCard,
  onboarding_progress: OnboardingProgressCard,
  ticket_created: ({ data }) => (
    <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900 shadow-sm">
      <p className="font-semibold">Ticket {data.ticket_id} created</p>
      <p className="text-xs">Status: {data.status}</p>
    </div>
  ),
};

export default function ChatWindow({ messages, cards, loading }) {
  const endRef = useRef(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, cards, loading]);

  // Interleave messages and cards by timestamp.
  const stream = [
    ...messages.map((m) => ({ ts: m.ts, kind: "message", payload: m })),
    ...cards.map((c) => ({ ts: c.ts, kind: "card", payload: c })),
  ].sort((a, b) => a.ts - b.ts);

  return (
    <div className="flex-1 overflow-y-auto p-4">
      <div className="mx-auto flex max-w-3xl flex-col gap-3">
        {stream.length === 0 && (
          <div className="rounded-xl border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500">
            Start by describing your IT issue. Try:{" "}
            <span className="font-medium text-slate-700">
              "My system is slow"
            </span>
          </div>
        )}
        {stream.map((item, idx) => {
          if (item.kind === "message") {
            return (
              <MessageBubble
                key={idx}
                role={item.payload.role}
                text={item.payload.text}
              />
            );
          }
          const Renderer = CARD_RENDERERS[item.payload.kind];
          if (!Renderer) return null;
          return <Renderer key={idx} data={item.payload.data} />;
        })}
        {loading && <LoadingIndicator />}
        <div ref={endRef} />
      </div>
    </div>
  );
}
