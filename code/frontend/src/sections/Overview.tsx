import { StatusCard, type StatusTone } from '../components/StatusCard'

interface OverviewProps {
  apiStatusLabel: string
  apiStatusTone: StatusTone
}

export function Overview({ apiStatusLabel, apiStatusTone }: Readonly<OverviewProps>) {
  return (
    <section id="quick-start" className="scroll-mt-28 space-y-6">
      <div>
        <p className="text-xs font-mono uppercase tracking-[0.22em] text-slate-500">Quick start</p>
        <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-100 sm:text-4xl">
          Operational visibility from one HTTPS endpoint
        </h2>
        <p className="mt-3 text-sm leading-7 text-slate-300 sm:text-base">
          Use the cards below to check live backend health and run network diagnostics against any host. All frontend
          and API traffic flows through port 443.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatusCard label="API health" value={apiStatusLabel} detail="GET /api/health" tone={apiStatusTone} />
        <StatusCard label="Runtime" value="Uvicorn HTTPS" detail="TLS endpoint on 443" tone="slate" />
        <StatusCard label="Active tools" value="Ping + Traceroute" detail="Looking glass diagnostics" tone="slate" />
        <StatusCard label="Frontend delivery" value="FastAPI served" detail="No external reverse proxy" tone="slate" />
      </div>
    </section>
  )
}