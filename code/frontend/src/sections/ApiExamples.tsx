import { ApiExample } from '../components/ApiExample'

export function ApiExamples() {
  return (
    <section id="api-examples" className="scroll-mt-28 space-y-6 rounded-2xl border border-slate-800/80 bg-slate-950/45 p-6">
      <div>
        <p className="text-xs font-mono uppercase tracking-[0.22em] text-slate-500">API examples</p>
        <h2 className="mt-2 text-2xl font-semibold text-slate-100">Simple operational commands</h2>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <ApiExample title="Health" command={'curl -k "https://localhost/api/health"'} />
        <ApiExample title="Ping" command={'curl -k "https://localhost/api/ping?host=cloudflare.com"'} />
        <ApiExample title="Traceroute" command={'curl -k "https://localhost/api/traceroute?host=google.com"'} />
      </div>

      <article id="deployment" className="scroll-mt-28 rounded-xl border border-slate-800/80 bg-slate-950/60 p-4">
        <h3 className="text-sm font-semibold text-slate-100">Deployment note</h3>
        <p className="mt-2 text-sm text-slate-300">
          Build frontend assets with <code className="font-mono text-cyan-300">npm run build</code>, then run backend.
          FastAPI serves both SPA and <code className="font-mono text-cyan-300">/api/*</code> routes on HTTPS port 443.
        </p>
      </article>
    </section>
  )
}