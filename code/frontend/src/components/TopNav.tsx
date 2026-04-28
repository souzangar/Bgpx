import clsx from 'clsx'
import { Activity, Search } from 'lucide-react'

import { BrandMark } from './BrandMark'

export type HealthIndicatorTone = 'success' | 'warning' | 'error' | 'pending'

interface TopNavProps {
  healthLabel: string
  healthTone: HealthIndicatorTone
  onFocusPrimaryInput: () => void
}

const healthClassName: Record<HealthIndicatorTone, string> = {
  success: 'border-emerald-400/35 bg-emerald-950/30 text-emerald-200',
  warning: 'border-amber-400/35 bg-amber-950/30 text-amber-200',
  error: 'border-red-400/35 bg-red-950/30 text-red-200',
  pending: 'border-slate-600/70 bg-slate-900/70 text-slate-300',
}

export function TopNav({ healthLabel, healthTone, onFocusPrimaryInput }: Readonly<TopNavProps>) {
  return (
    <header className="sticky top-0 z-40 border-b border-white/10 bg-slate-950/70 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-3 px-4 sm:h-20 sm:gap-4">
        <BrandMark />

        <button
          type="button"
          onClick={onFocusPrimaryInput}
          className="ml-auto hidden h-11 w-full max-w-xl items-center justify-between rounded-xl border border-slate-700/80 bg-slate-900/60 px-4 text-left text-sm text-slate-400 transition hover:border-cyan-400/40 hover:text-slate-200 md:flex"
          aria-label="Focus host input"
        >
          <span className="inline-flex items-center gap-2">
            <Search className="h-4 w-4" />
            Search hosts, prefixes, ASNs
          </span>
          <kbd className="rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-500">⌘K</kbd>
        </button>

        <span
          className={clsx(
            'inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold tracking-wide',
            healthClassName[healthTone],
          )}
        >
          <Activity className="h-3.5 w-3.5" />
          {healthLabel}
        </span>

        <a
          href="https://github.com/souzangar/Bgpx"
          target="_blank"
          rel="noreferrer"
          className="hidden rounded-lg border border-slate-700/80 p-2 text-slate-300 transition hover:border-cyan-400/40 hover:text-cyan-300 sm:inline-flex"
          aria-label="Open project repository"
        >
          <svg viewBox="0 0 19 19" className="h-4 w-4" fill="currentColor" aria-hidden="true">
            <path
              fillRule="evenodd"
              d="M9.356 1.85C5.05 1.85 1.57 5.356 1.57 9.694a7.84 7.84 0 0 0 5.324 7.44c.387.079.528-.168.528-.376 0-.182-.013-.805-.013-1.454-2.165.467-2.616-.935-2.616-.935-.349-.91-.864-1.143-.864-1.143-.71-.48.051-.48.051-.48.787.051 1.2.805 1.2.805.695 1.194 1.817.857 2.268.649.064-.507.27-.857.49-1.052-1.728-.182-3.545-.857-3.545-3.87 0-.857.31-1.558.8-2.104-.078-.195-.349-1 .077-2.078 0 0 .657-.208 2.14.805a7.5 7.5 0 0 1 1.946-.26c.657 0 1.328.092 1.946.26 1.483-1.013 2.14-.805 2.14-.805.426 1.078.155 1.883.078 2.078.502.546.799 1.247.799 2.104 0 3.013-1.818 3.675-3.558 3.87.284.247.528.714.528 1.454 0 1.052-.012 1.896-.012 2.156 0 .208.142.455.528.377a7.84 7.84 0 0 0 5.324-7.441c.013-4.338-3.48-7.844-7.773-7.844"
              clipRule="evenodd"
            />
          </svg>
        </a>
      </div>
    </header>
  )
}