import clsx from 'clsx'
import { Activity, Search, SquareArrowOutUpRight } from 'lucide-react'

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

export function TopNav({ healthLabel, healthTone, onFocusPrimaryInput }: TopNavProps) {
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
          <SquareArrowOutUpRight className="h-4 w-4" />
        </a>
      </div>
    </header>
  )
}