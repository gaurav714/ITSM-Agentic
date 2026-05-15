import { useState } from "react";

export default function ChatInput({ onSend, disabled }) {
  const [text, setText] = useState("");

  const submit = (e) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      submit(e);
    }
  };

  return (
    <form
      onSubmit={submit}
      className="flex items-end gap-2 border-t border-slate-200 bg-white p-4"
    >
      <textarea
        value={text}
        disabled={disabled}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Describe your IT issue (e.g. 'My system is slow')"
        rows={1}
        className="max-h-36 min-h-11 flex-1 resize-none rounded-lg border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20 disabled:bg-slate-100"
      />
      <button
        type="submit"
        disabled={disabled || !text.trim()}
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-brand text-white shadow-sm shadow-brand/20 transition hover:bg-brand-dark disabled:cursor-not-allowed disabled:bg-slate-300"
        aria-label="Send message"
      >
        <svg
          aria-hidden="true"
          className="h-5 w-5"
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="2"
          viewBox="0 0 24 24"
        >
          <path d="m22 2-7 20-4-9-9-4 20-7Z" />
          <path d="M22 2 11 13" />
        </svg>
      </button>
    </form>
  );
}
