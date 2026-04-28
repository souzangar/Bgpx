import { Gauge, Route } from 'lucide-react'

import { Button } from '../components/Button'
import { ResultPanel } from '../components/ResultPanel'
import { TextInput } from '../components/TextInput'
import { ToolCard } from '../components/ToolCard'
import { formatMs, formatPercent } from '../lib/format'
import type {
  PingResponse,
  RequestState,
  TracerouteHopResponse,
  TracerouteResponse,
} from '../lib/types'

interface ToolsProps {
  pingHost: string
  pingValidationError: string | null
  pingState: RequestState<PingResponse>
  onPingHostChange: (value: string) => void
  onRunPing: () => void

  tracerouteHost: string
  tracerouteValidationError: string | null
  tracerouteState: RequestState<TracerouteResponse>
  onTracerouteHostChange: (value: string) => void
  onRunTraceroute: () => void
}

type FormSubmitEvent = Parameters<NonNullable<React.ComponentProps<'form'>['onSubmit']>>[0]

function PingSummary({ result }: Readonly<{ result: PingResponse }>) {
  return (
    <dl className="grid gap-3 sm:grid-cols-3">
      <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
        <dt className="text-xs uppercase tracking-[0.16em] text-slate-500">Status</dt>
        <dd className="mt-1 text-sm font-semibold text-slate-100">{result.message}</dd>
      </div>
      <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
        <dt className="text-xs uppercase tracking-[0.16em] text-slate-500">Latency</dt>
        <dd className="mt-1 text-sm font-semibold text-slate-100">{formatMs(result.ping_time_ms)}</dd>
      </div>
      <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
        <dt className="text-xs uppercase tracking-[0.16em] text-slate-500">TTL</dt>
        <dd className="mt-1 text-sm font-semibold text-slate-100">{result.ttl ?? '—'}</dd>
      </div>
    </dl>
  )
}

function TracerouteTable({ hops }: Readonly<{ hops: TracerouteHopResponse[] }>) {
  if (hops.length === 0) {
    return <p className="text-sm text-slate-400">No hops returned.</p>
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-800">
      <table className="min-w-full border-collapse text-sm text-slate-200">
        <thead className="bg-slate-900/80 text-left text-xs uppercase tracking-[0.16em] text-slate-400">
          <tr>
            <th className="px-3 py-2">Hop</th>
            <th className="px-3 py-2">Address</th>
            <th className="px-3 py-2">Average RTT</th>
            <th className="px-3 py-2">Loss</th>
          </tr>
        </thead>
        <tbody>
          {hops.slice(0, 12).map((hop) => (
            <tr key={`${hop.distance}-${hop.address}`} className="border-t border-slate-800/70">
              <td className="px-3 py-2 font-mono text-slate-300">{hop.distance}</td>
              <td className="px-3 py-2 font-mono text-cyan-200">{hop.address}</td>
              <td className="px-3 py-2">{formatMs(hop.avg_rtt_ms)}</td>
              <td className="px-3 py-2">{formatPercent(hop.packet_loss * 100)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Tools({
  pingHost,
  pingValidationError,
  pingState,
  onPingHostChange,
  onRunPing,
  tracerouteHost,
  tracerouteValidationError,
  tracerouteState,
  onTracerouteHostChange,
  onRunTraceroute,
}: Readonly<ToolsProps>) {
  const handlePingSubmit = (event: FormSubmitEvent) => {
    event.preventDefault()
    onRunPing()
  }

  const handleTracerouteSubmit = (event: FormSubmitEvent) => {
    event.preventDefault()
    onRunTraceroute()
  }

  return (
    <section className="space-y-5">
      <ToolCard
        id="ping"
        icon={Gauge}
        title="Ping"
        description="Run a single ICMP probe and return latency, TTL, and status message."
      >
        <form className="space-y-4" onSubmit={handlePingSubmit}>
          <TextInput
            id="ping-host"
            label="Target host"
            value={pingHost}
            placeholder="1.1.1.1 or cloudflare.com"
            onChange={onPingHostChange}
          />
          {pingValidationError ? (
            <div className="rounded-xl border border-amber-400/30 bg-amber-950/30 p-4 text-sm text-amber-100">
              {pingValidationError}
            </div>
          ) : null}
          <div className="flex justify-end">
            <Button type="submit" disabled={pingState.loading}>
              {pingState.loading ? 'Running ping...' : 'Run ping'}
            </Button>
          </div>
        </form>
        <ResultPanel
          loading={pingState.loading}
          loadingMessage="Running ping..."
          error={pingState.error}
          data={pingState.data}
          emptyMessage="Submit a host to view ping output."
        >
          {pingState.data ? <PingSummary result={pingState.data} /> : null}
        </ResultPanel>
      </ToolCard>

      <ToolCard
        id="traceroute"
        icon={Route}
        title="Traceroute"
        description="Inspect path hops, latency, and packet loss to your target destination."
      >
        <form className="space-y-4" onSubmit={handleTracerouteSubmit}>
          <TextInput
            id="traceroute-host"
            label="Target host"
            value={tracerouteHost}
            placeholder="8.8.8.8 or google.com"
            onChange={onTracerouteHostChange}
          />
          {tracerouteValidationError ? (
            <div className="rounded-xl border border-amber-400/30 bg-amber-950/30 p-4 text-sm text-amber-100">
              {tracerouteValidationError}
            </div>
          ) : null}
          <div className="flex justify-end">
            <Button type="submit" disabled={tracerouteState.loading}>
              {tracerouteState.loading ? 'Tracing route...' : 'Run traceroute'}
            </Button>
          </div>
        </form>
        <ResultPanel
          loading={tracerouteState.loading}
          loadingMessage="Tracing route..."
          error={tracerouteState.error}
          data={tracerouteState.data}
          emptyMessage="Submit a host to view traceroute hops."
        >
          {tracerouteState.data ? <TracerouteTable hops={tracerouteState.data.hops} /> : null}
        </ResultPanel>
      </ToolCard>
    </section>
  )
}