import type { ReactNode } from 'react'

import { formatJson } from '../lib/format'
import { CodeBlock } from './CodeBlock'

interface ResultPanelProps {
  loading: boolean
  loadingMessage: string
  error: string | null
  data: unknown
  emptyMessage: string
  children?: ReactNode
}

export function ResultPanel({
  loading,
  loadingMessage,
  error,
  data,
  emptyMessage,
  children,
}: ResultPanelProps) {
  if (loading) {
    return (
      <div className="rounded-xl border border-sky-400/25 bg-sky-950/30 p-4 text-sm text-sky-100">
        {loadingMessage}
      </div>
    )
  }

  if (error) {
    return <div className="rounded-xl border border-red-400/30 bg-red-950/30 p-4 text-sm text-red-100">{error}</div>
  }

  if (!data) {
    return (
      <div className="rounded-xl border border-slate-800/80 bg-slate-950/70 p-4 text-sm text-slate-400">{emptyMessage}</div>
    )
  }

  return (
    <div className="space-y-4 rounded-xl border border-slate-800/80 bg-slate-950/70 p-4">
      {children}
      <details>
        <summary className="cursor-pointer text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
          Raw JSON
        </summary>
        <div className="mt-3">
          <CodeBlock code={formatJson(data)} />
        </div>
      </details>
    </div>
  )
}