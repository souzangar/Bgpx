export function BackgroundDecor() {
  return (
    <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden" aria-hidden="true">
      <div className="bg-grid absolute inset-0 opacity-40" />

      <div className="absolute -left-20 top-20 h-72 w-72 rounded-full bg-cyan-500/20 blur-3xl" />
      <div className="absolute right-0 top-10 h-72 w-72 rounded-full bg-indigo-500/20 blur-3xl" />

      <span className="circuit-line left-[18%] top-0 h-[38rem]" />
      <span className="circuit-line left-[62%] top-20 h-[30rem]" />
      <span className="circuit-line left-[83%] top-10 h-[26rem]" />
    </div>
  )
}