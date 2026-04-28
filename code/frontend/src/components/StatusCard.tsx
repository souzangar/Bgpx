import clsx from 'clsx'

export type StatusTone = 'green' | 'amber' | 'red' | 'slate'

interface StatusCardProps {
  label: string
  value: string
  detail: string
  tone?: StatusTone
}

const toneClasses: Record<StatusTone, string> = {
  green: 'border-emerald-400/30 bg-emerald-950/25 text-emerald-200',
  amber: 'border-amber-400/30 bg-amber-950/25 text-amber-200',
  red: 'border-red-400/30 bg-red-950/25 text-red-200',
  slate: 'border-slate-700/80 bg-slate-900/60 text-slate-200',
}

export function StatusCard({ label, value, detail, tone = 'slate' }: Readonly<StatusCardProps>) {
  return (
    <article className={clsx('rounded-xl border p-4', toneClasses[tone])}>
      <p className="text-xs font-mono uppercase tracking-[0.22em] text-slate-400">{label}</p>
      <p className="mt-2 text-base font-semibold">{value}</p>
      <p className="mt-1 text-sm text-slate-300">{detail}</p>
    </article>
  )
}