import { Link } from "react-router-dom";

export default function Header() {
  return (
    <header className="flex h-[78px] items-center justify-between border-b border-slate-100 bg-white px-6 shadow-sm shadow-slate-200/30 lg:px-[60px]">
      <Link to="/" className="flex items-center gap-1.5" aria-label="Zoe home">
        <span className="text-[30px] font-black leading-none tracking-normal text-slate-950">
          zoe
        </span>
        <span className="-mt-5 h-2.5 w-4 rotate-[20deg] rounded-sm bg-brand" />
      </Link>
      <nav className="hidden items-center gap-2 text-[15px] font-medium text-slate-600 md:flex">
        <Link
          to="/chat"
          className="flex h-11 items-center gap-2 rounded-lg bg-brand px-4 text-white shadow-sm shadow-brand/20 transition hover:bg-brand-dark"
        >
          <Icon name="play" />
          Live Demo
        </Link>
        <Link
          to="/tickets"
          className="flex h-11 items-center gap-2 rounded-lg px-3 transition hover:bg-slate-50 hover:text-slate-950"
        >
          <Icon name="grid" />
          Executive Dashboard
        </Link>
        <Link
          to="/settings"
          className="flex h-11 items-center gap-2 rounded-lg px-3 transition hover:bg-slate-50 hover:text-slate-950"
        >
          <Icon name="nodes" />
          Architecture
        </Link>
      </nav>
      <nav className="flex items-center gap-2">
        <Link
          to="/chat/system_slow_diagnostics"
          className="flex h-11 items-center gap-2 rounded-lg bg-slate-950 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800"
        >
          <Icon name="spark" />
          Start live demo
        </Link>
      </nav>
    </header>
  );
}

function Icon({ name }) {
  const paths = {
    play: <path d="M8 5v14l11-7-11-7Z" />,
    grid: <path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z" />,
    nodes: <path d="M12 5v5M7 19v-4h10v4M5 19h4M15 19h4M9 10h6v5H9z" />,
    spark: (
      <>
        <path d="M12 3l1.7 5.2L19 10l-5.3 1.8L12 17l-1.7-5.2L5 10l5.3-1.8L12 3Z" />
        <path d="M5 3v4M3 5h4M19 17v4M17 19h4" />
      </>
    ),
  };

  return (
    <svg
      aria-hidden="true"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.8"
      viewBox="0 0 24 24"
    >
      {paths[name]}
    </svg>
  );
}
