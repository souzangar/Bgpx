import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

interface ToolCardProps {
  id: string
  title: string
  description: string
  icon: LucideIcon
  children: ReactNode
}

export function ToolCard({ id, title, description, icon: Icon, children }: Readonly<ToolCardProps>) {
  return (
    <section
      id={id}
      className="scroll-mt-28 space-y-5 rounded-2xl border border-slate-800/80 bg-slate-950/50 p-6 shadow-2xl shadow-slate-950/40"
      aria-label={title}
    >
      <div className="flex items-start gap-4">
        <div className="rounded-lg border border-cyan-400/30 bg-cyan-400/10 p-2 text-cyan-300">
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <h3 className="text-base font-semibold text-slate-100">{title}</h3>
          <p className="mt-1 text-sm text-slate-400">{description}</p>
        </div>
      </div>
      {children}
    </section>
  )
}