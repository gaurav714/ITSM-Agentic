import { Link } from "react-router-dom";

export default function Header() {
  return (
    <header className="flex h-14 items-center justify-between border-b border-slate-200 bg-white px-6 shadow-sm">
      <Link to="/" className="flex items-center gap-2">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand text-white font-bold">
          AI
        </span>
        <span className="font-semibold text-slate-800">Helpdesk Assistant</span>
      </Link>
      <nav className="flex gap-4 text-sm text-slate-600">
        <Link to="/" className="hover:text-brand">
          Home
        </Link>
        <Link to="/chat" className="hover:text-brand">
          Chat
        </Link>
        <Link to="/tickets" className="hover:text-brand">
          Tickets
        </Link>
        <Link to="/settings" className="hover:text-brand">
          Settings
        </Link>
      </nav>
    </header>
  );
}
