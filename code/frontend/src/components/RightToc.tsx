const tocLinks = [
  { href: '#quick-start', label: 'Quick start' },
  { href: '#health', label: 'Health' },
  { href: '#ping', label: 'Ping' },
  { href: '#traceroute', label: 'Traceroute' },
  { href: '#api-examples', label: 'API examples' },
  { href: '#deployment', label: 'Deployment' },
]

export function RightToc() {
  return (
    <aside className="sticky top-24 hidden h-[calc(100vh-7rem)] xl:block" aria-label="Table of contents">
      <p className="mb-4 text-sm font-semibold text-slate-100">On this page</p>
      <ul className="space-y-2">
        {tocLinks.map((link) => (
          <li key={link.href}>
            <a href={link.href} className="text-sm text-slate-400 transition hover:text-slate-100">
              {link.label}
            </a>
          </li>
        ))}
      </ul>
    </aside>
  )
}