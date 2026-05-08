import { Gauge, Route, type LucideIcon } from 'lucide-react'
import { useMemo, useState } from 'react'

import { fetchIpGeolocationLookup } from '../lib/api'
import { Button } from '../components/Button'
import { ResultPanel } from '../components/ResultPanel'
import { TextInput } from '../components/TextInput'
import { ToolCard } from '../components/ToolCard'
import { formatMs, formatPercent } from '../lib/format'
import type {
  AsnLookupData,
  CountryLookupData,
  IpLookupData,
  IpLookupResponse,
  IpLookupTargetType,
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

type ToolTab = 'ping' | 'traceroute'
type IpToolTab = 'ip-lookup' | 'asn-lookup' | 'country-lookup'
const LOOKUP_PAGE_SIZE = 15

interface ToolTabConfig {
  id: ToolTab
  title: string
  description: string
  icon: LucideIcon
}

interface IpToolTabConfig {
  id: IpToolTab
  title: string
  description: string
}

const toolTabs: ToolTabConfig[] = [
  {
    id: 'ping',
    title: 'Ping',
    description: 'Run a single ICMP probe and return latency, TTL, and status message.',
    icon: Gauge,
  },
  {
    id: 'traceroute',
    title: 'Traceroute',
    description: 'Inspect path hops, latency, and packet loss to your target destination.',
    icon: Route,
  },
]

const ipToolTabs: IpToolTabConfig[] = [
  {
    id: 'ip-lookup',
    title: 'IP Lookup',
    description: 'Lookup geolocation and network details for an IP address.',
  },
  {
    id: 'asn-lookup',
    title: 'ASN Lookup',
    description: 'Lookup metadata and location scope for an autonomous system number.',
  },
  {
    id: 'country-lookup',
    title: 'Country Lookup',
    description: 'Lookup IP network allocations and statistics for a country code.',
  },
]

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
            <th className="px-3 py-2">Country</th>
            <th className="px-3 py-2">Average RTT</th>
            <th className="px-3 py-2">Loss</th>
          </tr>
        </thead>
        <tbody>
          {hops.slice(0, 12).map((hop) => (
            <tr key={`${hop.distance}-${hop.address}`} className="border-t border-slate-800/70">
              <td className="px-3 py-2 font-mono text-slate-300">{hop.distance}</td>
              <td className="px-3 py-2 font-mono text-cyan-200">{hop.address}</td>
              <td className="px-3 py-2 font-mono">{formatCountryCell(hop.country_code)}</td>
              <td className="px-3 py-2">{formatMs(hop.avg_rtt_ms)}</td>
              <td className="px-3 py-2">{formatPercent(hop.packet_loss * 100)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function formatCountryCell(countryCode: string | null): string {
  const normalized = (countryCode ?? '').trim().toUpperCase()
  if (!/^[A-Z]{2}$/.test(normalized)) {
    return 'N/A'
  }

  const base = 127397
  const flag = String.fromCodePoint(
    normalized.charCodeAt(0) + base,
    normalized.charCodeAt(1) + base,
  )

  return `${flag} ${normalized}`
}

function IpLookupSummary({ data }: Readonly<{ data: IpLookupData }>) {
  return (
    <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
        <dt className="text-xs uppercase tracking-[0.16em] text-slate-500">IP</dt>
        <dd className="mt-1 font-mono text-sm text-slate-100">{data.ip}</dd>
      </div>
      <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
        <dt className="text-xs uppercase tracking-[0.16em] text-slate-500">Network</dt>
        <dd className="mt-1 font-mono text-sm text-slate-100">{data.network ?? 'N/A'}</dd>
      </div>
      <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
        <dt className="text-xs uppercase tracking-[0.16em] text-slate-500">Country</dt>
        <dd className="mt-1 text-sm text-slate-100">{data.country ?? 'N/A'}</dd>
      </div>
      <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
        <dt className="text-xs uppercase tracking-[0.16em] text-slate-500">Country Code</dt>
        <dd className="mt-1 text-sm text-slate-100">{formatCountryCell(data.country_code)}</dd>
      </div>
      <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
        <dt className="text-xs uppercase tracking-[0.16em] text-slate-500">ASN</dt>
        <dd className="mt-1 font-mono text-sm text-slate-100">{data.asn ?? 'N/A'}</dd>
      </div>
      <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
        <dt className="text-xs uppercase tracking-[0.16em] text-slate-500">Domain</dt>
        <dd className="mt-1 text-sm text-slate-100">{data.as_domain ?? 'N/A'}</dd>
      </div>
    </dl>
  )
}

function AsnLookupTable({ data }: Readonly<{ data: AsnLookupData }>) {
  const [page, setPage] = useState(1)
  const [goToPageInput, setGoToPageInput] = useState('1')
  const totalPages = Math.max(1, Math.ceil(data.items.length / LOOKUP_PAGE_SIZE))
  const currentPage = Math.min(page, totalPages)
  const start = (currentPage - 1) * LOOKUP_PAGE_SIZE
  const pageItems = data.items.slice(start, start + LOOKUP_PAGE_SIZE)

  const goToPage = () => {
    const numeric = Number.parseInt(goToPageInput, 10)
    if (Number.isNaN(numeric)) {
      setGoToPageInput(String(currentPage))
      return
    }
    const nextPage = Math.min(totalPages, Math.max(1, numeric))
    setPage(nextPage)
    setGoToPageInput(String(nextPage))
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-300">
        <span className="font-mono text-slate-100">{data.asn}</span>
        {data.as_name ? <span> - {data.as_name}</span> : null} · {data.total} network(s)
      </p>
      <div className="overflow-x-auto rounded-xl border border-slate-800">
        <table className="min-w-full border-collapse text-sm text-slate-200">
          <thead className="bg-slate-900/80 text-left text-xs uppercase tracking-[0.16em] text-slate-400">
            <tr>
              <th className="px-3 py-2">Network</th>
              <th className="px-3 py-2">Country</th>
              <th className="px-3 py-2">Continent</th>
            </tr>
          </thead>
          <tbody>
            {pageItems.map((item, index) => (
              <tr key={`${item.network}-${index}`} className="border-t border-slate-800/70">
                <td className="px-3 py-2 font-mono text-cyan-200">{item.network}</td>
                <td className="px-3 py-2">{item.country} ({formatCountryCell(item.country_code)})</td>
                <td className="px-3 py-2">{item.continent} ({item.continent_code})</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center justify-center gap-3">
        <button
          type="button"
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          disabled={currentPage === 1}
          className="rounded-md border border-slate-700/80 px-3 py-1 text-xs text-slate-300 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Previous
        </button>

        <div className="flex items-center gap-2 text-xs text-slate-300">
          <span>
            Page {currentPage} / {totalPages}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <input
            type="number"
            min={1}
            max={totalPages}
            value={goToPageInput}
            onChange={(event) => setGoToPageInput(event.target.value)}
            className="w-16 rounded-md border border-slate-700/80 bg-slate-950/40 px-2 py-1 text-xs text-slate-200"
          />
          <button
            type="button"
            onClick={goToPage}
            className="rounded-md border border-slate-700/80 px-3 py-1 text-xs text-slate-300"
          >
            Go
          </button>
        </div>

        <button
          type="button"
          onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          disabled={currentPage === totalPages}
          className="rounded-md border border-slate-700/80 px-3 py-1 text-xs text-slate-300 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Next
        </button>
      </div>
    </div>
  )
}

function CountryLookupTable({ data }: Readonly<{ data: CountryLookupData }>) {
  const [page, setPage] = useState(1)
  const [goToPageInput, setGoToPageInput] = useState('1')
  const totalPages = Math.max(1, Math.ceil(data.items.length / LOOKUP_PAGE_SIZE))
  const currentPage = Math.min(page, totalPages)
  const start = (currentPage - 1) * LOOKUP_PAGE_SIZE
  const pageItems = data.items.slice(start, start + LOOKUP_PAGE_SIZE)

  const goToPage = () => {
    const numeric = Number.parseInt(goToPageInput, 10)
    if (Number.isNaN(numeric)) {
      setGoToPageInput(String(currentPage))
      return
    }
    const nextPage = Math.min(totalPages, Math.max(1, numeric))
    setPage(nextPage)
    setGoToPageInput(String(nextPage))
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-300">
        <span className="font-mono text-slate-100">{data.country}</span> · {data.total} network(s)
      </p>
      <div className="overflow-x-auto rounded-xl border border-slate-800">
        <table className="min-w-full border-collapse text-sm text-slate-200">
          <thead className="bg-slate-900/80 text-left text-xs uppercase tracking-[0.16em] text-slate-400">
            <tr>
              <th className="px-3 py-2">Network</th>
              <th className="px-3 py-2">Continent</th>
              <th className="px-3 py-2">ASN</th>
            </tr>
          </thead>
          <tbody>
            {pageItems.map((item, index) => (
              <tr key={`${item.network}-${index}`} className="border-t border-slate-800/70">
                <td className="px-3 py-2 font-mono text-cyan-200">{item.network}</td>
                <td className="px-3 py-2">{item.continent} ({item.continent_code})</td>
                <td className="px-3 py-2 font-mono">
                  {item.asn ? (
                    <>
                      {item.asn}
                      {item.as_name ? ` - ${item.as_name}` : ''}
                    </>
                  ) : (
                    'N/A'
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center justify-center gap-3">
        <button
          type="button"
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          disabled={currentPage === 1}
          className="rounded-md border border-slate-700/80 px-3 py-1 text-xs text-slate-300 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Previous
        </button>

        <div className="flex items-center gap-2 text-xs text-slate-300">
          <span>
            Page {currentPage} / {totalPages}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <input
            type="number"
            min={1}
            max={totalPages}
            value={goToPageInput}
            onChange={(event) => setGoToPageInput(event.target.value)}
            className="w-16 rounded-md border border-slate-700/80 bg-slate-950/40 px-2 py-1 text-xs text-slate-200"
          />
          <button
            type="button"
            onClick={goToPage}
            className="rounded-md border border-slate-700/80 px-3 py-1 text-xs text-slate-300"
          >
            Go
          </button>
        </div>

        <button
          type="button"
          onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          disabled={currentPage === totalPages}
          className="rounded-md border border-slate-700/80 px-3 py-1 text-xs text-slate-300 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Next
        </button>
      </div>
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
  const [activeTab, setActiveTab] = useState<ToolTab>('ping')
  const [activeIpTab, setActiveIpTab] = useState<IpToolTab>('ip-lookup')
  const [ipLookupValue, setIpLookupValue] = useState('1.1.1.1')
  const [asnLookupValue, setAsnLookupValue] = useState('AS13335')
  const [countryLookupValue, setCountryLookupValue] = useState('US')
  const [ipLookupValidationError, setIpLookupValidationError] = useState<string | null>(null)
  const [asnLookupValidationError, setAsnLookupValidationError] = useState<string | null>(null)
  const [countryLookupValidationError, setCountryLookupValidationError] = useState<string | null>(null)
  const [ipLookupState, setIpLookupState] = useState<RequestState<IpLookupResponse>>({ loading: false, error: null, data: null })
  const [asnLookupState, setAsnLookupState] = useState<RequestState<IpLookupResponse>>({ loading: false, error: null, data: null })
  const [countryLookupState, setCountryLookupState] = useState<RequestState<IpLookupResponse>>({ loading: false, error: null, data: null })

  const handlePingSubmit = (event: FormSubmitEvent) => {
    event.preventDefault()
    onRunPing()
  }

  const handleTracerouteSubmit = (event: FormSubmitEvent) => {
    event.preventDefault()
    onRunTraceroute()
  }

  const runLookup = async (
    targetType: IpLookupTargetType,
    value: string,
    setValidationError: (error: string | null) => void,
    setState: (state: RequestState<IpLookupResponse>) => void,
  ) => {
    const normalized = value.trim()
    const validationError = normalized ? null : 'Value is required.'
    setValidationError(validationError)

    if (validationError) {
      return
    }

    setState({ loading: true, error: null, data: null })

    try {
      const result = await fetchIpGeolocationLookup({ type: targetType, value: normalized })
      if (result.status === 'failure') {
        setState({ loading: false, error: result.error.message, data: result })
        return
      }
      setState({ loading: false, error: null, data: result })
    } catch (error) {
      setState({ loading: false, error: error instanceof Error ? error.message : 'Lookup request failed', data: null })
    }
  }

  const activeTool = useMemo(
    () => toolTabs.find((tool) => tool.id === activeTab) ?? toolTabs[0],
    [activeTab],
  )

  const ActiveToolIcon = activeTool.icon
  const activeIpTool = useMemo(
    () => ipToolTabs.find((tool) => tool.id === activeIpTab) ?? ipToolTabs[0],
    [activeIpTab],
  )

  return (
    <section className="space-y-5">
      <ToolCard id="network-tools" icon={ActiveToolIcon} title="Network tools" description={activeTool.description}>
          <div className="rounded-xl border border-slate-800/70 bg-slate-900/40 p-2">
            <div className="grid gap-2 sm:grid-cols-2">
              {toolTabs.map((tool) => {
                const isActive = tool.id === activeTab
                return (
                  <button
                    key={tool.id}
                    type="button"
                    className={`rounded-lg border px-3 py-2 text-left transition ${
                      isActive
                        ? 'border-cyan-400/50 bg-cyan-400/10 text-cyan-200'
                        : 'border-slate-700/80 bg-slate-950/30 text-slate-300 hover:border-slate-600 hover:text-slate-100'
                    }`}
                    onClick={() => setActiveTab(tool.id)}
                    aria-pressed={isActive}
                  >
                    <p className="text-xs font-mono uppercase tracking-[0.14em]">{tool.title}</p>
                  </button>
                )
              })}
            </div>
          </div>

          {activeTab === 'ping' ? (
            <>
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
            </>
          ) : null}

          {activeTab === 'traceroute' ? (
            <>
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
            </>
          ) : null}
      </ToolCard>

      <ToolCard
        id="ip-tools"
        icon={Gauge}
        title="IP Tools"
        description={activeIpTool.description}
      >
          <div className="rounded-xl border border-slate-800/70 bg-slate-900/40 p-2">
            <div className="grid gap-2 sm:grid-cols-3">
              {ipToolTabs.map((tool) => {
                const isActive = tool.id === activeIpTab
                return (
                  <button
                    key={tool.id}
                    type="button"
                    className={`rounded-lg border px-3 py-2 text-left transition ${
                      isActive
                        ? 'border-cyan-400/50 bg-cyan-400/10 text-cyan-200'
                        : 'border-slate-700/80 bg-slate-950/30 text-slate-300 hover:border-slate-600 hover:text-slate-100'
                    }`}
                    onClick={() => setActiveIpTab(tool.id)}
                    aria-pressed={isActive}
                  >
                    <p className="text-xs font-mono uppercase tracking-[0.14em]">{tool.title}</p>
                  </button>
                )
              })}
            </div>
          </div>

          {activeIpTab === 'ip-lookup' ? (
            <>
              <form className="space-y-4" onSubmit={(event) => {
                event.preventDefault()
                void runLookup('ip', ipLookupValue, setIpLookupValidationError, setIpLookupState)
              }}>
                <TextInput id="ip-lookup-value" label="IP address" value={ipLookupValue} placeholder="1.1.1.1" onChange={setIpLookupValue} />
                {ipLookupValidationError ? <div className="rounded-xl border border-amber-400/30 bg-amber-950/30 p-4 text-sm text-amber-100">{ipLookupValidationError}</div> : null}
                <div className="flex justify-end">
                  <Button type="submit" disabled={ipLookupState.loading}>{ipLookupState.loading ? 'Looking up IP...' : 'Run IP lookup'}</Button>
                </div>
              </form>
              <ResultPanel loading={ipLookupState.loading} loadingMessage="Looking up IP..." error={ipLookupState.error} data={ipLookupState.data} emptyMessage="Submit an IP to view geolocation details.">
                {ipLookupState.data && ipLookupState.data.status === 'success' && 'ip' in ipLookupState.data.data ? <IpLookupSummary data={ipLookupState.data.data as IpLookupData} /> : null}
              </ResultPanel>
            </>
          ) : null}

          {activeIpTab === 'asn-lookup' ? (
            <>
              <form className="space-y-4" onSubmit={(event) => {
                event.preventDefault()
                void runLookup('asn', asnLookupValue, setAsnLookupValidationError, setAsnLookupState)
              }}>
                <TextInput id="asn-lookup-value" label="ASN" value={asnLookupValue} placeholder="AS13335" onChange={setAsnLookupValue} />
                {asnLookupValidationError ? <div className="rounded-xl border border-amber-400/30 bg-amber-950/30 p-4 text-sm text-amber-100">{asnLookupValidationError}</div> : null}
                <div className="flex justify-end">
                  <Button type="submit" disabled={asnLookupState.loading}>{asnLookupState.loading ? 'Looking up ASN...' : 'Run ASN lookup'}</Button>
                </div>
              </form>
              <ResultPanel loading={asnLookupState.loading} loadingMessage="Looking up ASN..." error={asnLookupState.error} data={asnLookupState.data} emptyMessage="Submit an ASN to view matched networks.">
                {asnLookupState.data && asnLookupState.data.status === 'success' && 'asn' in asnLookupState.data.data ? <AsnLookupTable data={asnLookupState.data.data as AsnLookupData} /> : null}
              </ResultPanel>
            </>
          ) : null}

          {activeIpTab === 'country-lookup' ? (
            <>
              <form className="space-y-4" onSubmit={(event) => {
                event.preventDefault()
                void runLookup('country', countryLookupValue, setCountryLookupValidationError, setCountryLookupState)
              }}>
                <TextInput id="country-lookup-value" label="Country code" value={countryLookupValue} placeholder="US" onChange={setCountryLookupValue} />
                {countryLookupValidationError ? <div className="rounded-xl border border-amber-400/30 bg-amber-950/30 p-4 text-sm text-amber-100">{countryLookupValidationError}</div> : null}
                <div className="flex justify-end">
                  <Button type="submit" disabled={countryLookupState.loading}>{countryLookupState.loading ? 'Looking up country...' : 'Run country lookup'}</Button>
                </div>
              </form>
              <ResultPanel loading={countryLookupState.loading} loadingMessage="Looking up country..." error={countryLookupState.error} data={countryLookupState.data} emptyMessage="Submit a country code to view matched networks.">
                {countryLookupState.data && countryLookupState.data.status === 'success' && 'country' in countryLookupState.data.data ? <CountryLookupTable data={countryLookupState.data.data as CountryLookupData} /> : null}
              </ResultPanel>
            </>
          ) : null}
      </ToolCard>
    </section>
  )
}