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

export interface RequestState<T> {
  loading: boolean
  error: string | null
  data: T | null
}