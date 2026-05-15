import { useNavigate } from "react-router-dom";

const capabilityNodes = [
  { label: "Actions", icon: "bolt", className: "left-[24%] top-[8%]" },
  { label: "Voice I/O", icon: "wave", className: "right-[24%] top-[8%]" },
  { label: "Voice Agent", icon: "briefcase", className: "right-[3%] top-[43%]" },
  { label: "Orchestrator", icon: "nodes", className: "right-[24%] bottom-[8%]" },
  { label: "Reasoning", icon: "chip", className: "left-[24%] bottom-[8%]" },
  { label: "Guardrails", icon: "shield", className: "left-[3%] top-[43%]" },
];

const proofPoints = [
  ["Resolves in seconds", "Average 42 s end-to-end"],
  ["Proactive self-healing", "Detects issues before users notice"],
  ["Voice native", "Hands-free, phone-friendly, accessible"],
];

export default function HelpdeskHomePage() {
  const navigate = useNavigate();
  const startApp = () => navigate("/chat");

  return (
    <div className="h-full overflow-y-auto bg-[#071426] text-white">
      <header className="sticky top-0 z-20 border-b border-slate-200/80 bg-slate-200 px-6 py-4 text-slate-700 shadow-sm">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
          <button
            type="button"
            onClick={() => navigate("/")}
            className="flex items-center gap-1 text-3xl font-black tracking-tight text-slate-950"
            aria-label="Zoé home"
          >
            zoé
            <span className="mb-5 h-2 w-4 rotate-[25deg] rounded-sm bg-blue-600" />
          </button>

          <nav className="hidden items-center gap-10 text-base font-medium text-slate-600 md:flex">
            <button
              type="button"
              onClick={startApp}
              className="flex items-center gap-2 hover:text-slate-950"
            >
              <Icon name="play" className="h-5 w-5" />
              Live Demo
            </button>
            <button
              type="button"
              className="flex items-center gap-2 hover:text-slate-950"
            >
              <Icon name="grid" className="h-5 w-5" />
              Executive Dashboard
            </button>
            <button
              type="button"
              className="flex items-center gap-2 hover:text-slate-950"
            >
              <Icon name="architecture" className="h-5 w-5" />
              Architecture
            </button>
          </nav>

          <button
            type="button"
            onClick={startApp}
            className="flex items-center gap-2 rounded-lg bg-slate-950 px-5 py-3 text-sm font-bold text-white shadow-lg shadow-slate-900/20 transition hover:bg-blue-700 sm:text-base"
          >
            <Icon name="sparkle" className="h-5 w-5" />
            Start App
          </button>
        </div>
      </header>

      <section className="relative min-h-[calc(100vh-73px)] overflow-hidden">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(96,165,250,0.06)_1px,transparent_1px),linear-gradient(to_bottom,rgba(96,165,250,0.05)_1px,transparent_1px)] bg-[size:76px_76px]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_72%_50%,rgba(37,99,235,0.2),transparent_34%),linear-gradient(90deg,rgba(17,24,58,0.96),rgba(5,19,32,0.98))]" />

        <div className="relative mx-auto grid min-h-[calc(100vh-73px)] max-w-7xl items-center gap-12 px-6 py-14 lg:grid-cols-[1fr_0.95fr] lg:px-8">
          <div className="max-w-3xl">
            <div className="inline-flex items-center gap-3 rounded-full border border-blue-400/50 bg-blue-500/15 px-4 py-2 text-sm font-semibold text-slate-200 shadow-inner shadow-blue-400/10">
              <Icon name="sparkle" className="h-4 w-4 text-blue-200" />
              Zoé Axon - Autonomous IT Service Management
            </div>

            <h1 className="mt-8 text-5xl font-black leading-[1.05] tracking-normal text-white sm:text-6xl lg:text-7xl">
              Meet <span className="text-blue-500">Zoé</span>.
              <br />
              The future of voice
              <br />
              for IT support.
            </h1>

            <p className="mt-8 max-w-2xl text-xl leading-8 text-slate-200">
              Zoé resolves L1-L3 tickets autonomously - password resets, slow
              laptops, VPN failures, software requests - in seconds, not hours.
              Watch her work live.
            </p>

            <div className="mt-10 flex flex-col gap-4 sm:flex-row">
              <button
                type="button"
                onClick={startApp}
                className="flex min-h-14 items-center justify-center gap-3 rounded-lg bg-blue-600 px-7 py-4 text-lg font-bold text-white shadow-xl shadow-blue-950/30 transition hover:bg-blue-500"
              >
                <Icon name="play" className="h-5 w-5" />
                Start App
                <Icon name="arrowRight" className="h-5 w-5" />
              </button>
              <button
                type="button"
                className="flex min-h-14 items-center justify-center gap-3 rounded-lg border border-white/25 bg-white/5 px-7 py-4 text-lg font-bold text-white transition hover:border-blue-300 hover:bg-white/10"
              >
                <Icon name="chart" className="h-5 w-5" />
                Executive dashboard
              </button>
            </div>

            <div className="mt-14 space-y-6">
              {proofPoints.map(([title, detail]) => (
                <div
                  key={title}
                  className="flex flex-wrap items-center gap-3 text-base"
                >
                  <Icon name="bolt" className="h-5 w-5 shrink-0 text-sky-300" />
                  <span className="font-bold text-white">{title}</span>
                  <span className="text-slate-500">-</span>
                  <span className="text-slate-400">{detail}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="relative mx-auto flex aspect-square w-full max-w-[620px] items-center justify-center">
            <div className="absolute inset-[4%] rounded-full border border-slate-400/15" />
            <div className="absolute inset-[13%] rounded-full border border-slate-400/15" />
            <div className="absolute inset-[23%] rounded-full border border-blue-300/10" />
            <div className="absolute inset-[29%] rounded-full border border-blue-300/10" />
            <div className="absolute inset-[35%] rounded-full border border-blue-300/10" />
            <div className="absolute inset-[41%] rounded-full border border-blue-300/10" />
            <div className="absolute inset-[18%] rounded-full bg-blue-600/5 shadow-[0_0_90px_rgba(37,99,235,0.2)]" />

            <div className="z-10 flex h-[32%] w-[32%] flex-col items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-indigo-700 shadow-2xl shadow-blue-950/60">
              <div className="text-5xl font-black tracking-normal">zoé</div>
              <div className="mt-1 text-xs font-semibold tracking-[0.5em] text-blue-100">
                CORE AI
              </div>
            </div>

            {capabilityNodes.map((node) => (
              <div
                key={node.label}
                className={`absolute flex -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-2 text-center ${node.className}`}
              >
                <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-slate-400/25 bg-slate-900/65 text-slate-200 shadow-lg shadow-slate-950/40 backdrop-blur">
                  <Icon name={node.icon} className="h-5 w-5" />
                </div>
                <span className="font-mono text-xs font-bold text-slate-200">
                  {node.label}
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

function Icon({ name, className = "h-5 w-5" }) {
  const common = {
    className,
    fill: "none",
    stroke: "currentColor",
    strokeLinecap: "round",
    strokeLinejoin: "round",
    strokeWidth: 2,
    viewBox: "0 0 24 24",
    "aria-hidden": "true",
  };

  const paths = {
    architecture: (
      <>
        <path d="M12 4v5" />
        <path d="M8 9h8v5H8z" />
        <path d="M12 14v3" />
        <path d="M6 17h12" />
        <path d="M4 17h4v4H4z" />
        <path d="M16 17h4v4h-4z" />
      </>
    ),
    arrowRight: <path d="M5 12h14m-6-6 6 6-6 6" />,
    bolt: <path d="m13 2-8 12h7l-1 8 8-12h-7z" />,
    briefcase: (
      <>
        <path d="M10 6V5a2 2 0 0 1 2-2h0a2 2 0 0 1 2 2v1" />
        <path d="M4 7h16v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" />
        <path d="M9 12h6" />
      </>
    ),
    chart: (
      <>
        <path d="M4 19V5" />
        <path d="M4 19h16" />
        <path d="M8 17v-6" />
        <path d="M12 17V7" />
        <path d="M16 17v-4" />
      </>
    ),
    chip: (
      <>
        <rect x="7" y="7" width="10" height="10" rx="2" />
        <path d="M9 1v4M15 1v4M9 19v4M15 19v4M1 9h4M1 15h4M19 9h4M19 15h4" />
        <rect x="10" y="10" width="4" height="4" />
      </>
    ),
    grid: (
      <>
        <rect x="4" y="4" width="6" height="6" />
        <rect x="14" y="4" width="6" height="6" />
        <rect x="4" y="14" width="6" height="6" />
        <rect x="14" y="14" width="6" height="6" />
      </>
    ),
    nodes: (
      <>
        <circle cx="7" cy="7" r="3" />
        <circle cx="17" cy="17" r="3" />
        <path d="M10 7h3a4 4 0 0 1 4 4v3" />
        <path d="M7 10v3a4 4 0 0 0 4 4h3" />
      </>
    ),
    play: <path d="m8 5 11 7-11 7z" />,
    shield: <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />,
    sparkle: (
      <>
        <path d="M12 3 9.8 8.8 4 11l5.8 2.2L12 19l2.2-5.8L20 11l-5.8-2.2z" />
        <path d="M19 3v4" />
        <path d="M21 5h-4" />
      </>
    ),
    wave: (
      <>
        <path d="M4 10v4" />
        <path d="M8 7v10" />
        <path d="M12 4v16" />
        <path d="M16 7v10" />
        <path d="M20 10v4" />
      </>
    ),
  };

  return <svg {...common}>{paths[name]}</svg>;
}
