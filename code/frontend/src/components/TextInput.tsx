interface TextInputProps {
  id: string
  label: string
  value: string
  placeholder?: string
  description?: string
  disabled?: boolean
  onChange: (next: string) => void
}

export function TextInput({
  id,
  label,
  value,
  placeholder,
  description,
  disabled = false,
  onChange,
}: Readonly<TextInputProps>) {
  return (
    <div className="space-y-2">
      <label htmlFor={id} className="block text-sm font-medium text-slate-200">
        {label}
      </label>
      {description ? <p className="text-xs text-slate-400">{description}</p> : null}
      <input
        id={id}
        name={id}
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-xl border border-slate-700/80 bg-slate-950/60 px-4 py-3 text-sm text-slate-100 outline-none focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/20 disabled:cursor-not-allowed disabled:opacity-60"
      />
    </div>
  )
}