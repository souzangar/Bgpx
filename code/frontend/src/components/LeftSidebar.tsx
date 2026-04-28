const navGroups = [
  {
    title: 'Overview',
    items: [
      { href: '#quick-start', label: 'Getting started', active: true },
      { href: '#health', label: 'System health' },
    ],
  },
  {
    title: 'Looking Glass',
    items: [
      { href: '#ping', label: 'Ping' },
      { href: '#traceroute', label: 'Traceroute' },
      { href: '#', label: 'BGP lookup (coming soon)' },
      { href: '#', label: 'ASN lookup (coming soon)' },
      { href: '#', label: 'Prefix lookup (coming soon)' },
    ],
  },
  {
    title: 'Operations',
    items: [
      { href: '#health', label: 'API status' },
      { href: '#api-examples', label: 'Examples' },
      { href: '#deployment', label: 'Troubleshooting' },
    ],
  },
]

export function LeftSidebar() {
  return (
    <nav className="sticky top-24 hidden h-[calc(100vh-7rem)] overflow-auto pr-3 md:block" aria-label="Sidebar navigation">
      {navGroups.map((group) => (
        <div key={group.title} className="mb-7">
          <p className="mb-3 text-xs font-mono uppercase tracking-[0.22em] text-slate-500">{group.title}</p>
          <ul className="space-y-2">
            {group.items.map((item) => (
              <li key={item.label}>
                <a
                  href={item.href}
                  className={
                    item.active
                      ? 'block border-l border-cyan-400 pl-4 text-sm text-cyan-300'
                      : 'block border-l border-slate-800 pl-4 text-sm text-slate-400 transition hover:text-slate-200'
                  }
                  aria-current={item.active ? 'page' : undefined}
                >
                  {item.label}
                </a>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  )
}