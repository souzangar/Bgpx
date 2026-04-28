import clsx from 'clsx'

interface CodeBlockProps {
  code: string
  className?: string
}

export function CodeBlock({ code, className }: Readonly<CodeBlockProps>) {
  return (
    <pre
      className={clsx(
        'overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/80 p-4 font-mono text-xs leading-6 text-slate-200 sm:text-sm',
        className,
      )}
    >
      <code>{code}</code>
    </pre>
  )
}