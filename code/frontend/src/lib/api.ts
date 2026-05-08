import type {
  ClientIpInfoResponse,
  HealthResponse,
  IpLookupRequestPayload,
  IpLookupResponse,
  PingResponse,
  TracerouteResponse,
} from './types'

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: 'application/json' },
    signal,
  })

  if (!response.ok) {
    const rawBody = await response.text()
    const detail = (() => {
      if (!rawBody) {
        return ''
      }

      try {
        const payload = JSON.parse(rawBody) as { detail?: unknown }
        if (typeof payload.detail === 'string') {
          return payload.detail
        }
        return JSON.stringify(payload)
      } catch {
        return rawBody
      }
    })()

    throw new Error(detail || `Request failed with status ${response.status}`)
  }

  return (await response.json()) as T
}

export function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return getJson<HealthResponse>('/api/health', signal)
}

export function fetchClientIpInfo(signal?: AbortSignal): Promise<ClientIpInfoResponse> {
  return getJson<ClientIpInfoResponse>('/api/client_ipinfo', signal)
}

export function fetchPing(host: string, signal?: AbortSignal): Promise<PingResponse> {
  return getJson<PingResponse>(`/api/ping?host=${encodeURIComponent(host)}`, signal)
}

export function fetchTraceroute(host: string, signal?: AbortSignal): Promise<TracerouteResponse> {
  return getJson<TracerouteResponse>(`/api/traceroute?host=${encodeURIComponent(host)}`, signal)
}

export async function fetchIpGeolocationLookup(
  payload: IpLookupRequestPayload,
  signal?: AbortSignal,
): Promise<IpLookupResponse> {
  const query = encodeURIComponent(JSON.stringify(payload))
  return getJson<IpLookupResponse>(`/api/ipinfo?request=${query}`, signal)
}