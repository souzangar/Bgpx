import { Button } from '../components/Button'
import type { ClientIpInfoResponse, RequestState } from '../lib/types'

interface HeroProps {
  onRunCheck: () => void
  onViewExamples: () => void
  clientIpInfoState: RequestState<ClientIpInfoResponse>
}

const fieldRows: Array<{ label: string; key: keyof ClientIpInfoResponse }> = [
  { label: 'IP', key: 'ip' },
  { label: 'Network', key: 'network' },
  { label: 'Country', key: 'country' },
  { label: 'Country Code', key: 'country_code' },
  { label: 'Continent', key: 'continent' },
  { label: 'Continent Code', key: 'continent_code' },
  { label: 'ASN', key: 'asn' },
  { label: 'ASN Domain', key: 'as_domain' },
]

export function Hero({ onRunCheck, onViewExamples, clientIpInfoState }: Readonly<HeroProps>) {
  return (
    <section className="panel-highlight rounded-bgpx-panel border border-white/10 p-6 shadow-2xl shadow-cyan-950/20 backdrop-blur sm:p-8">
      <div className="grid gap-8 lg:grid-cols-2 lg:items-center">
        <div className="space-y-5">
          <p className="text-xs font-mono uppercase tracking-[0.22em] text-bgpx-cyan">BGPX Looking Glass</p>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-100 sm:text-4xl lg:text-5xl">
            {'Network diagnostics,'}
            {' '}
            <span className="bg-gradient-to-r from-cyan-300 via-sky-400 to-indigo-300 bg-clip-text text-transparent">
              exposed cleanly.
            </span>
          </h1>
          <p className="max-w-2xl text-xs leading-6 text-slate-300 sm:text-sm">
            BGPX is a lightweight looking glass for operational checks like ping and traceroute through a single
            HTTPS endpoint.
          </p>
          <div className="flex flex-wrap gap-3">
            <Button onClick={onRunCheck}>Run a check</Button>
            <Button variant="secondary" onClick={onViewExamples}>
              View API examples
            </Button>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-700/70 bg-slate-950/70 p-4 shadow-glow">
          <div className="mb-4 flex gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-red-400/70" />
            <span className="h-2.5 w-2.5 rounded-full bg-amber-400/70" />
            <span className="h-2.5 w-2.5 rounded-full bg-green-400/70" />
          </div>
          <p className="mb-3 text-[11px] font-mono uppercase tracking-[0.18em] text-slate-500">Client IP info</p>

          {clientIpInfoState.loading && (
            <div className="rounded-xl border border-slate-800/80 bg-slate-900/40 p-3 text-xs text-slate-400">
              Resolving client IP information...
            </div>
          )}

          {!clientIpInfoState.loading && clientIpInfoState.error && (
            <div className="rounded-xl border border-red-400/30 bg-red-950/30 p-3 text-xs text-red-100">
              Failed to load client IP info: {clientIpInfoState.error}
            </div>
          )}

          {!clientIpInfoState.loading && !clientIpInfoState.error && (
            <dl className="space-y-1.5 rounded-xl border border-slate-800/80 bg-slate-900/30 p-3">
              {fieldRows.map((row) => {
                const value = clientIpInfoState.data?.[row.key]
                return (
                  <div key={row.key} className="grid grid-cols-[8rem_minmax(0,1fr)] items-start gap-2 text-[11px]">
                    <dt className="font-mono uppercase tracking-[0.08em] text-slate-500">{row.label}</dt>
                    <dd className="break-all font-mono text-slate-200">{value ?? 'N/A'}</dd>
                  </div>
                )
              })}
            </dl>
          )}
        </div>
      </div>
    </section>
  )
}