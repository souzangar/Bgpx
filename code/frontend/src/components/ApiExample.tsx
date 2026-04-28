import { CodeBlock } from './CodeBlock'

interface ApiExampleProps {
  title: string
  command: string
}

export function ApiExample({ title, command }: ApiExampleProps) {
  return (
    <article className="space-y-3 rounded-xl border border-slate-800/80 bg-slate-950/60 p-4">
      <h3 className="text-sm font-semibold text-slate-100">{title}</h3>
      <CodeBlock code={command} />
    </article>
  )
}