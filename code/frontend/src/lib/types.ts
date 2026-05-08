export type ApiResult = 'success' | 'failure'

export interface HealthResponse {
  status: string
  service: string
}

export interface PingResponse {
  result: ApiResult
  ping_time_ms: number | null
  ttl: number | null
  message: string
}

export interface TracerouteHopResponse {
  distance: number
  address: string
  rtts_ms: number[]
  avg_rtt_ms: number
  min_rtt_ms: number
  max_rtt_ms: number
  packets_sent: number
  packets_received: number
  packet_loss: number
}

export interface TracerouteResponse {
  result: ApiResult
  hops: TracerouteHopResponse[]
  message: string
}

export interface ClientIpInfoResponse {
  ip: string | null
  network: string | null
  country: string | null
  country_code: string | null
  continent: string | null
  continent_code: string | null
  asn: string | null
  as_domain: string | null
}

export interface RequestState<T> {
  loading: boolean
  error: string | null
  data: T | null
}