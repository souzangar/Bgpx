export function BrandMark() {
  return (
    <div className="flex items-center gap-3">
      <svg viewBox="0 0 40 40" className="h-9 w-9 text-cyan-300" fill="none" aria-hidden="true">
        <path d="M12 5h16l8 15-8 15H12L4 20 12 5Z" stroke="currentColor" strokeWidth="2.5" />
        <path
          d="M12 5l8 15-8 15M28 5l-8 15 8 15M4 20h32"
          stroke="currentColor"
          strokeWidth="1.5"
          opacity="0.7"
        />
      </svg>
      <div>
        <p className="text-sm font-bold uppercase tracking-[0.25em] text-slate-100">BGPX</p>
        <p className="hidden text-xs text-slate-500 sm:block">Looking Glass</p>
      </div>
    </div>
  )
}