export default function MessageBubble({ role, text }) {
  const isUser = role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[82%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm leading-6 shadow-sm ${
          isUser
            ? "rounded-br-md bg-brand text-white shadow-brand/20"
            : "rounded-bl-md border border-slate-200 bg-white text-slate-800"
        }`}
      >
        {text}
      </div>
    </div>
  );
}
