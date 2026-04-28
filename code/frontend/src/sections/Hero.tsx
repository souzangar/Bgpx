import { Button } from '../components/Button'
import { CodeBlock } from '../components/CodeBlock'

interface HeroProps {
  onRunCheck: () => void
  onViewExamples: () => void
}

const heroCommands = `curl -k "https://localhost/api/ping?host=1.1.1.1"
curl -k "https://localhost/api/traceroute?host=8.8.8.8"`

export function Hero({ onRunCheck, onViewExamples }: Readonly<HeroProps>) {
  return (
    <section className="panel-highlight rounded-bgpx-panel border border-white/10 p-6 shadow-2xl shadow-cyan-950/20 backdrop-blur sm:p-8">
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-center">
        <div className="space-y-5">
          <p className="text-xs font-mono uppercase tracking-[0.22em] text-bgpx-cyan">BGPX Looking Glass</p>
          <h1 className="text-4xl font-semibold tracking-tight text-slate-100 sm:text-5xl lg:text-6xl">
            {'Network diagnostics,'}
            {' '}
            <span className="bg-gradient-to-r from-cyan-300 via-sky-400 to-indigo-300 bg-clip-text text-transparent">
              exposed cleanly.
            </span>
          </h1>
          <p className="max-w-2xl text-sm leading-7 text-slate-300 sm:text-base">
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
          <CodeBlock code={heroCommands} className="border-none bg-transparent p-0" />
        </div>
      </div>
    </section>
  )
}