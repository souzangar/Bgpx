import type { HealthResponse, PingResponse, TracerouteResponse } from './types'

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: 'application/json' },
    signal,
  })

  if (!response.ok) {
    const detail = await (async () => {
      try {
        const payload = await response.json()
        return typeof payload?.detail === 'string' ? payload.detail : JSON.stringify(payload)
      } catch {
        return response.text()
      }
    })()

    throw new Error(detail || `Request failed with status ${response.status}`)
  }

  return (await response.json()) as T
}

export function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return getJson<HealthResponse>('/api/health', signal)
}

export function fetchPing(host: string, signal?: AbortSignal): Promise<PingResponse> {
  return getJson<PingResponse>(`/api/ping?host=${encodeURIComponent(host)}`, signal)
}

export function fetchTraceroute(host: string, signal?: AbortSignal): Promise<TracerouteResponse> {
  return getJson<TracerouteResponse>(`/api/traceroute?host=${encodeURIComponent(host)}`, signal)
}