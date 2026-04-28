# BGPX Frontend Action Plan

This document is the implementation blueprint for the first BGPX frontend. It is written so a future task can implement the UI without re-deciding architecture, styling, layout, or deployment behavior.

## 1. Goals

Build a production-ready frontend in `code/frontend` for the existing FastAPI backend.

Primary requirements:

- Use **Vite** for the frontend build system.
- Use **React + TypeScript** for the UI.
- Use **Tailwind CSS** for styling.
- Do **not** introduce nginx, Caddy, Traefik, Apache, or any other reverse proxy.
- Serve the production frontend behind the existing **Uvicorn/FastAPI** process.
- Expose only **TCP 443** to the network.
- Keep backend API routes under `/api/*`.
- Implement an original dark UI inspired by the supplied screenshots, without copying paid/proprietary Tailwind UI source code.

## 2. Licensing and Theme Guidance

Tailwind CSS itself is open-source and free to use.

Do **not** copy paid Tailwind UI templates, component source, private assets, or proprietary examples unless the project has a valid license and intentionally stores that licensed code in this repository.

Allowed approach:

- Use Tailwind CSS utilities freely.
- Recreate the visual direction from screenshots using original markup and CSS.
- Use similar design traits: dark navy background, cyan/violet highlights, glass cards, grid lines, terminal/code styling, documentation-style navigation.
- Avoid copying exact proprietary component code, exact SVG assets, or template structure from paid products.

## 3. Recommended Stack

Frontend directory: `code/frontend`

Recommended packages:

```bash
npm create vite@latest . -- --template react-ts
npm install
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

Optional but useful packages:

```bash
npm install clsx lucide-react
```

Package purpose:

- `vite`: fast dev server and production build.
- `react`, `react-dom`: UI runtime.
- `typescript`: safer API and component code.
- `tailwindcss`: utility-first styling.
- `postcss`, `autoprefixer`: Tailwind build pipeline.
- `clsx`: conditional class names.
- `lucide-react`: icons for search, terminal, activity, network, copy, alert states.

## 4. Backend Serving Model

The backend currently runs with Uvicorn HTTPS on port `443` by default:

```python
uvicorn.run(
    "main:app",
    host=host,
    port=port,
    ssl_certfile=str(ssl_files.cert_file),
    ssl_keyfile=str(ssl_files.key_file),
    reload=True,
    reload_dirs=[str(backend_dir)],
)
```

Production serving target:

- Browser connects to `https://<host>/` on TCP 443.
- FastAPI serves the SPA shell and frontend assets.
- API remains available at `https://<host>/api/...`.

Recommended route behavior:

| URL | Owner | Behavior |
| --- | --- | --- |
| `/api/health` | FastAPI API | Backend health endpoint |
| `/api/ping?host=1.1.1.1` | FastAPI API | Backend ping endpoint |
| `/api/traceroute?host=1.1.1.1` | FastAPI API | Backend traceroute endpoint |
| `/assets/*` | FastAPI static files | Vite-built JS/CSS/assets |
| `/` | FastAPI frontend fallback | Serve `dist/index.html` |
| Any non-API path | FastAPI frontend fallback | Serve `dist/index.html` for SPA routing |

Recommended FastAPI implementation concept:

```python
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def create_app() -> FastAPI:
    app = FastAPI(title="BGPX Backend", version="0.1.0")
    app.include_router(api_router, prefix="/api")

    project_root = Path(__file__).resolve().parents[1]
    frontend_dist = project_root / "frontend" / "dist"
    assets_dir = frontend_dist / "assets"

    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str):
        index_file = frontend_dist / "index.html"
        if not index_file.exists():
            raise HTTPException(status_code=404, detail="Frontend build not found. Run npm run build in code/frontend.")
        return FileResponse(index_file)

    return app
```

Important implementation notes:

- Register `/api` before the catch-all frontend route.
- Do not catch `/api/*` in the SPA fallback.
- Only mount frontend static files if `dist` exists, so backend tests/imports still work before the frontend is built.
- For Vite, use relative or root-safe asset paths. Default Vite output under `/assets/...` works with the mount above.
- If adding React Router later, FastAPI fallback must serve `index.html` for non-API deep links.

## 5. Development Workflow

Recommended local development:

1. Backend:

   ```bash
   cd code/backend
   python main.py
   ```

2. Frontend dev server:

   ```bash
   cd code/frontend
   npm run dev
   ```

3. Configure Vite dev proxy so frontend API calls can use `/api`:

   ```ts
   // vite.config.ts
   import { defineConfig } from 'vite'
   import react from '@vitejs/plugin-react'

   export default defineConfig({
     plugins: [react()],
     server: {
       proxy: {
         '/api': {
           target: 'https://localhost:443',
           changeOrigin: true,
           secure: false,
         },
       },
     },
   })
   ```

Production/local integrated test:

```bash
cd code/frontend
npm run build

cd ../backend
python main.py
```

Then open:

```text
https://localhost/
```

## 6. UI Product Direction

The first frontend should be a **BGP Looking Glass dashboard with a documentation-style shell**.

It should feel like the screenshots:

- Dark technical documentation page.
- Top navigation with logo and command/search field.
- Left sidebar navigation.
- Center content column with hero, tool cards, forms, and results.
- Optional right “On this page” table of contents on large screens.
- Decorative grid lines, glows, and glassy panels.

But the content should be for BGPX:

- Health status.
- Ping tool.
- Traceroute tool.
- Future navigation placeholders for BGP, DNS, WHOIS, route lookup, ASN lookup, prefix lookup.

## 7. Visual Design System

### 7.1 Color Palette

Use Tailwind config extensions for exact colors.

```ts
// tailwind.config.ts theme.extend.colors
colors: {
  bgpx: {
    ink: '#E5F0FF',
    muted: '#94A3B8',
    subtle: '#64748B',
    black: '#020617',
    navy: '#07111F',
    navy2: '#0B1628',
    panel: '#0F1B2E',
    panel2: '#111F35',
    line: '#21314A',
    line2: '#2B3D5B',
    cyan: '#38BDF8',
    cyan2: '#0EA5E9',
    cyan3: '#67E8F9',
    violet: '#6366F1',
    violet2: '#8B5CF6',
    green: '#22C55E',
    amber: '#F59E0B',
    red: '#EF4444',
  },
}
```

Color usage:

- Page background: `#020617` and `#07111F`.
- Main panels: `#0F1B2E` with transparency.
- Borders: `#21314A`, hover border `#2B3D5B`.
- Primary accent: cyan `#38BDF8`.
- Secondary accent: violet `#6366F1`.
- Text primary: `#E5F0FF`.
- Text secondary: `#94A3B8`.
- Text tertiary: `#64748B`.
- Success: `#22C55E`.
- Warning: `#F59E0B`.
- Error: `#EF4444`.

### 7.2 CSS Variables

Add global variables in `src/index.css`:

```css
:root {
  color-scheme: dark;
  --bgpx-black: #020617;
  --bgpx-navy: #07111f;
  --bgpx-panel: #0f1b2e;
  --bgpx-panel-2: #111f35;
  --bgpx-line: #21314a;
  --bgpx-line-2: #2b3d5b;
  --bgpx-ink: #e5f0ff;
  --bgpx-muted: #94a3b8;
  --bgpx-subtle: #64748b;
  --bgpx-cyan: #38bdf8;
  --bgpx-violet: #6366f1;
}

html {
  scroll-behavior: smooth;
  background: var(--bgpx-black);
}

body {
  min-height: 100vh;
  margin: 0;
  background:
    radial-gradient(circle at 18% 12%, rgba(56, 189, 248, 0.18), transparent 28rem),
    radial-gradient(circle at 78% 8%, rgba(99, 102, 241, 0.14), transparent 26rem),
    linear-gradient(180deg, #07111f 0%, #020617 45%, #020617 100%);
  color: var(--bgpx-ink);
}

::selection {
  background: rgba(56, 189, 248, 0.28);
  color: #ffffff;
}
```

### 7.3 Background Grid

Implement a reusable `.bg-grid` utility:

```css
.bg-grid {
  background-image:
    linear-gradient(rgba(148, 163, 184, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(148, 163, 184, 0.08) 1px, transparent 1px);
  background-size: 64px 64px;
  mask-image: linear-gradient(to bottom, black, transparent 85%);
}
```

Decorative circuit lines can be approximated with absolutely positioned elements:

```css
.circuit-line {
  position: absolute;
  width: 1px;
  background: linear-gradient(to bottom, transparent, rgba(56, 189, 248, 0.32), transparent);
}
```

### 7.4 Typography

Use a modern system stack to avoid external font dependency:

```css
font-family:
  Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
  "Segoe UI", sans-serif;
```

Monospace stack:

```css
font-family:
  "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
```

Recommended type scale:

| Element | Tailwind classes |
| --- | --- |
| Hero title | `text-4xl sm:text-5xl lg:text-6xl font-semibold tracking-tight` |
| Page title | `text-3xl sm:text-4xl font-semibold tracking-tight` |
| Section heading | `text-xl sm:text-2xl font-semibold` |
| Card title | `text-base font-semibold` |
| Body | `text-sm sm:text-base leading-7 text-slate-300` |
| Metadata | `text-xs font-mono uppercase tracking-[0.22em] text-slate-500` |
| Code/result | `text-xs sm:text-sm font-mono leading-6` |

### 7.5 Borders, Radii, Shadows

Recommended tokens:

```ts
borderRadius: {
  'bgpx-card': '1.25rem',
  'bgpx-panel': '1.5rem',
}
```

Common classes:

- Main panel: `rounded-2xl border border-white/10 bg-slate-950/45 shadow-2xl shadow-cyan-950/20 backdrop-blur`
- Card: `rounded-xl border border-slate-800/80 bg-slate-900/45 hover:border-cyan-400/40 transition`
- Input: `rounded-xl border border-slate-700/80 bg-slate-950/60 px-4 py-3 text-slate-100 outline-none focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/20`
- Button primary: `rounded-full bg-cyan-300 px-5 py-2.5 text-sm font-semibold text-slate-950 hover:bg-cyan-200`
- Button secondary: `rounded-full bg-slate-800 px-5 py-2.5 text-sm font-semibold text-slate-100 hover:bg-slate-700`

### 7.6 Gradients

Primary accent text:

```html
<span className="bg-gradient-to-r from-cyan-300 via-sky-400 to-indigo-300 bg-clip-text text-transparent">
  BGP intelligence
</span>
```

Panel highlight:

```css
.panel-highlight {
  background:
    linear-gradient(180deg, rgba(15, 27, 46, 0.88), rgba(2, 6, 23, 0.72)),
    radial-gradient(circle at top right, rgba(56, 189, 248, 0.14), transparent 22rem);
}
```

### 7.7 Scrollbar

```css
* {
  scrollbar-width: thin;
  scrollbar-color: rgba(100, 116, 139, 0.7) rgba(15, 23, 42, 0.6);
}

*::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}

*::-webkit-scrollbar-track {
  background: rgba(15, 23, 42, 0.6);
}

*::-webkit-scrollbar-thumb {
  background: rgba(100, 116, 139, 0.7);
  border-radius: 999px;
  border: 2px solid rgba(15, 23, 42, 0.6);
}
```

## 8. Layout Plan

### 8.1 App Shell

Desktop layout:

```text
┌──────────────────────────────────────────────────────────────┐
│ TopNav: logo, search/command bar, status, GitHub placeholder  │
├───────────────┬────────────────────────────────┬─────────────┤
│ LeftSidebar   │ MainContent                    │ RightTOC    │
│ navigation    │ hero, tools, results, docs     │ anchors     │
└───────────────┴────────────────────────────────┴─────────────┘
```

Responsive behavior:

- `< 768px`: hide desktop sidebars; use compact top navigation and stacked content.
- `768px - 1279px`: show left sidebar, hide right TOC.
- `>= 1280px`: show left sidebar, main content, and right TOC.

Suggested top-level classes:

```tsx
<div className="min-h-screen bg-bgpx-black text-bgpx-ink">
  <BackgroundDecor />
  <TopNav />
  <div className="mx-auto grid max-w-7xl grid-cols-1 gap-8 px-4 py-8 md:grid-cols-[16rem_minmax(0,1fr)] xl:grid-cols-[16rem_minmax(0,1fr)_14rem]">
    <LeftSidebar />
    <main className="min-w-0 space-y-10">...</main>
    <RightToc />
  </div>
</div>
```

### 8.2 Top Navigation

Contents:

- Logo mark: hex/network icon built with CSS or simple SVG.
- Text: `BGPX` plus subtitle `Looking Glass` on larger screens.
- Search/command bar visual: `Search hosts, prefixes, ASNs` with `⌘K` badge. It can be non-functional initially or focus the main input.
- API health pill.
- GitHub/documentation icon placeholders.

Styling:

```tsx
<header className="sticky top-0 z-40 border-b border-white/10 bg-slate-950/70 backdrop-blur-xl">
```

### 8.3 Left Sidebar Navigation

Sections:

- Overview
  - Getting started
  - System health
- Looking Glass
  - Ping
  - Traceroute
  - BGP lookup (coming soon)
  - ASN lookup (coming soon)
  - Prefix lookup (coming soon)
- Operations
  - API status
  - Examples
  - Troubleshooting

Active item style:

```tsx
className="border-l border-cyan-400 pl-4 text-cyan-300"
```

Inactive item style:

```tsx
className="border-l border-slate-800 pl-4 text-slate-400 hover:text-slate-200"
```

### 8.4 Right Table of Contents

Anchors:

- Quick start
- Health
- Ping
- Traceroute
- API examples
- Deployment

Style should match screenshot right rail:

```tsx
<aside className="sticky top-24 hidden h-[calc(100vh-7rem)] xl:block">
  <p className="mb-4 text-sm font-semibold text-slate-100">On this page</p>
  ...
</aside>
```

## 9. Main Page Content

### 9.1 Hero Section

Purpose:

- Explain BGPX clearly.
- Give immediate access to Ping and Traceroute tools.
- Show a code/config style preview to match screenshots.

Hero copy draft:

```text
Network diagnostics, exposed cleanly.

BGPX is a lightweight looking glass for running operational checks like ping and traceroute through a single HTTPS endpoint.
```

CTA buttons:

- `Run a check` scrolls/focuses Ping form.
- `View API examples` scrolls to examples section.

Code card content:

```bash
curl -k "https://localhost/api/ping?host=1.1.1.1"
curl -k "https://localhost/api/traceroute?host=8.8.8.8"
```

### 9.2 Status Strip

Cards:

- API Health
- HTTPS/Uvicorn
- Active tools
- Frontend served by FastAPI

Example visual classes:

```tsx
<div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
  <StatusCard label="API" value="Online" tone="green" />
</div>
```

### 9.3 Tool Cards

Implement cards for:

1. Health Check
2. Ping
3. Traceroute

Each card should include:

- Icon.
- Short explanation.
- Form/input if needed.
- Submit button.
- Loading state.
- Error state.
- Result panel.

Recommended card shell:

```tsx
<section className="rounded-2xl border border-slate-800/80 bg-slate-950/50 p-6 shadow-2xl shadow-slate-950/40">
```

### 9.4 API Examples Section

Show examples in code blocks:

```bash
curl -k "https://localhost/api/health"
curl -k "https://localhost/api/ping?host=cloudflare.com"
curl -k "https://localhost/api/traceroute?host=google.com"
```

Style code blocks:

```tsx
<pre className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/80 p-4 text-sm text-slate-200">
```

## 10. Component Architecture

Recommended source tree:

```text
code/frontend/
├── index.html
├── package.json
├── postcss.config.js
├── tailwind.config.ts
├── tsconfig.json
├── vite.config.ts
└── src/
    ├── App.tsx
    ├── main.tsx
    ├── index.css
    ├── components/
    │   ├── ApiExample.tsx
    │   ├── BackgroundDecor.tsx
    │   ├── BrandMark.tsx
    │   ├── Button.tsx
    │   ├── CodeBlock.tsx
    │   ├── LeftSidebar.tsx
    │   ├── ResultPanel.tsx
    │   ├── RightToc.tsx
    │   ├── StatusCard.tsx
    │   ├── TextInput.tsx
    │   ├── ToolCard.tsx
    │   └── TopNav.tsx
    ├── lib/
    │   ├── api.ts
    │   ├── format.ts
    │   └── types.ts
    └── sections/
        ├── ApiExamples.tsx
        ├── Hero.tsx
        ├── Overview.tsx
        └── Tools.tsx
```

For the first implementation, it is acceptable to keep some components inside `App.tsx`, but the final code should remain easy to split.

## 11. API Integration Plan

Existing backend endpoints:

- `GET /api/health`
- `GET /api/ping?host=<target>`
- `GET /api/traceroute?host=<target>`

Use relative URLs so the same frontend works in development through Vite proxy and in production through Uvicorn:

```ts
export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: 'application/json' },
    signal,
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed with status ${response.status}`)
  }

  return response.json() as Promise<T>
}

export function fetchHealth(signal?: AbortSignal) {
  return getJson('/api/health', signal)
}

export function fetchPing(host: string, signal?: AbortSignal) {
  return getJson(`/api/ping?host=${encodeURIComponent(host)}`, signal)
}

export function fetchTraceroute(host: string, signal?: AbortSignal) {
  return getJson(`/api/traceroute?host=${encodeURIComponent(host)}`, signal)
}
```

### 11.1 Input Validation

Client-side validation should be simple and non-authoritative:

- Trim whitespace.
- Required target host for Ping and Traceroute.
- Maximum length around 253 characters.
- Allow hostnames, IPv4, IPv6-like strings.
- Show friendly error message before request if empty.

### 11.2 Loading States

For each tool:

- Disable submit button while loading.
- Show spinner/pulse indicator.
- Show text like `Running ping...` or `Tracing route...`.
- Use `AbortController` if implementing cancel/re-run behavior.

### 11.3 Error States

Error card style:

```tsx
<div className="rounded-xl border border-red-400/30 bg-red-950/30 p-4 text-sm text-red-100">
```

Warning card style:

```tsx
<div className="rounded-xl border border-amber-400/30 bg-amber-950/30 p-4 text-sm text-amber-100">
```

### 11.4 Result Display

First version can display formatted JSON:

```tsx
JSON.stringify(result, null, 2)
```

Recommended enhancement:

- For Ping: show transmitted/received/loss/latency if fields are available.
- For Traceroute: show hop list if fields are available.
- Always include collapsible raw JSON.

## 12. Accessibility Requirements

- Use semantic landmarks: `header`, `nav`, `main`, `section`, `aside`.
- Every input must have a visible or screen-reader label.
- Buttons must have clear text, not icon-only unless `aria-label` is present.
- Focus state must be visible with cyan ring.
- Color should not be the only signal for errors/success.
- Code blocks should be selectable and horizontally scrollable.
- Respect `prefers-reduced-motion`.

Reduced motion CSS:

```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
  }
}
```

## 13. Tailwind Configuration Details

Recommended `tailwind.config.ts`:

```ts
import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bgpx: {
          ink: '#E5F0FF',
          muted: '#94A3B8',
          subtle: '#64748B',
          black: '#020617',
          navy: '#07111F',
          navy2: '#0B1628',
          panel: '#0F1B2E',
          panel2: '#111F35',
          line: '#21314A',
          line2: '#2B3D5B',
          cyan: '#38BDF8',
          cyan2: '#0EA5E9',
          cyan3: '#67E8F9',
          violet: '#6366F1',
          violet2: '#8B5CF6',
          green: '#22C55E',
          amber: '#F59E0B',
          red: '#EF4444',
        },
      },
      boxShadow: {
        glow: '0 0 60px rgba(56, 189, 248, 0.18)',
        'glow-violet': '0 0 60px rgba(99, 102, 241, 0.16)',
      },
      fontFamily: {
        sans: [
          'Inter',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'sans-serif',
        ],
        mono: ['SFMono-Regular', 'Consolas', 'Liberation Mono', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [],
} satisfies Config
```

## 14. Original UI Elements Inspired by Screenshots

### 14.1 Brand Mark

Create a simple original SVG hex/network mark:

```tsx
export function BrandMark() {
  return (
    <div className="flex items-center gap-3">
      <svg viewBox="0 0 40 40" className="h-9 w-9 text-cyan-300" fill="none" aria-hidden="true">
        <path d="M12 5h16l8 15-8 15H12L4 20 12 5Z" stroke="currentColor" strokeWidth="2.5" />
        <path d="M12 5l8 15-8 15M28 5l-8 15 8 15M4 20h32" stroke="currentColor" strokeWidth="1.5" opacity="0.7" />
      </svg>
      <div>
        <p className="text-sm font-bold uppercase tracking-[0.25em] text-slate-100">BGPX</p>
        <p className="hidden text-xs text-slate-500 sm:block">Looking Glass</p>
      </div>
    </div>
  )
}
```

### 14.2 Terminal/Code Card

Use a card with small window dots and tabs:

```tsx
<div className="rounded-2xl border border-slate-700/70 bg-slate-950/70 p-4 shadow-glow">
  <div className="mb-4 flex gap-2">
    <span className="h-2.5 w-2.5 rounded-full bg-red-400/70" />
    <span className="h-2.5 w-2.5 rounded-full bg-amber-400/70" />
    <span className="h-2.5 w-2.5 rounded-full bg-green-400/70" />
  </div>
  <pre className="font-mono text-sm leading-7 text-slate-300">...</pre>
</div>
```

### 14.3 Grid Cards

Use card grids similar in mood to the component screenshot, but content should be operational BGPX features:

- Ping diagnostics.
- Traceroute path inspection.
- API-first design.
- Single-port deployment.
- TLS enabled.
- Future BGP route tools.

## 15. Implementation Phases

### Phase 1: Scaffold Frontend

- Initialize Vite React TypeScript in `code/frontend`.
- Install Tailwind.
- Configure Tailwind content paths.
- Add global CSS variables and base styles.
- Confirm `npm run dev` starts.
- Confirm `npm run build` produces `dist`.

### Phase 2: Build Static UI

- Implement app shell.
- Implement top nav.
- Implement left sidebar and right TOC.
- Implement hero and decorative code panel.
- Implement static status cards and tool cards.
- Match the dark/cyan/violet visual system.

### Phase 3: Connect APIs

- Add `src/lib/api.ts`.
- Wire health check on page load.
- Wire Ping form.
- Wire Traceroute form.
- Add loading/error/result states.
- Ensure all calls use relative `/api/...` URLs.

### Phase 4: Serve Through FastAPI/Uvicorn

- Update `code/backend/main.py` to serve `code/frontend/dist`.
- Mount `/assets` from Vite output.
- Add non-API fallback to `index.html`.
- Keep `/api/*` working.
- Keep backend import/tests working when `dist` does not exist.

### Phase 5: Verification

- Run frontend build.
- Start backend.
- Open `https://localhost/`.
- Verify `/api/health` still returns JSON.
- Verify `/api/ping?host=1.1.1.1` from UI.
- Verify `/api/traceroute?host=1.1.1.1` from UI.
- Verify deep frontend paths do not break if SPA routes are added later.

## 16. Acceptance Criteria

The implementation is complete when:

- `code/frontend` contains a Vite React TypeScript app.
- Tailwind CSS is configured and used.
- UI visually follows the provided screenshots using original implementation.
- Health, Ping, and Traceroute are callable from the browser UI.
- Production build is generated by `npm run build`.
- FastAPI/Uvicorn serves the frontend from `code/frontend/dist`.
- Only TCP 443 needs to be exposed for production access.
- `/api/*` routes continue to work independently from the frontend.
- No nginx or external reverse proxy is required.
- No paid Tailwind UI code/assets are copied into the repository.

## 17. Future Enhancements

- Add command palette for quick tool execution.
- Add history of recent checks in local storage.
- Add copy-to-clipboard buttons for results and curl commands.
- Add shareable URLs for tool state, e.g. `/?tool=ping&host=1.1.1.1`.
- Add structured traceroute hop visualization.
- Add BGP route lookup once backend endpoint exists.
- Add ASN/prefix lookup once backend endpoint exists.
- Add WebSocket or server-sent events if long-running diagnostics need streaming output.
