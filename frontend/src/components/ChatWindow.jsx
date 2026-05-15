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
    <div className="min-h-0 flex-1 overflow-y-auto bg-gradient-to-b from-white via-white to-slate-50/80 p-5">
      <div className="mx-auto flex max-w-2xl flex-col gap-3">
        {stream.length === 0 && (
          <div className="flex min-h-[420px] flex-col items-center justify-center text-center">
            <div className="mb-5 flex h-[70px] w-[70px] items-center justify-center rounded-full bg-brand/10 text-brand">
              <svg
                aria-hidden="true"
                className="h-7 w-7"
                fill="none"
                stroke="currentColor"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                viewBox="0 0 24 24"
              >
                <circle cx="12" cy="12" r="9" />
                <path d="M12 8h.01M11 12h1v5h1" />
              </svg>
            </div>
            <p className="text-base font-semibold text-slate-950">
              Press Play to start the conversation
            </p>
            <p className="mt-2 max-w-xs text-sm leading-6 text-slate-600">
              You will see a realistic interaction between a user and Zoe.
            </p>
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
