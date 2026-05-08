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
  country: string | null
  country_code: string | null
  asn: string | null
  as_name: string | null
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

export type IpLookupTargetType = 'ip' | 'asn' | 'country'

export interface IpLookupRequestPayload {
  type: IpLookupTargetType
  value: string
}

export interface IpLookupData {
  ip: string
  network: string | null
  country: string | null
  country_code: string | null
  continent: string | null
  continent_code: string | null
  asn: string | null
  as_name: string | null
  as_domain: string | null
}

export interface AsnLookupItem {
  network: string
  country: string
  country_code: string
  continent: string
  continent_code: string
}

export interface AsnLookupData {
  asn: string
  as_name: string | null
  total: number
  items: AsnLookupItem[]
}

export interface CountryLookupItem {
  network: string
  continent: string
  continent_code: string
  asn: string | null
  as_name: string | null
}

export interface CountryLookupData {
  country: string
  total: number
  items: CountryLookupItem[]
}

export interface IpLookupSuccessResponse {
  status: 'success'
  service_state: 'loading' | 'ready' | 'failed'
  resolution_state: 'found' | 'initializing_db' | 'not_found'
  data: IpLookupData | AsnLookupData | CountryLookupData
}

export interface IpLookupFailureResponse {
  status: 'failure'
  service_state: 'failed'
  error: {
    code: string
    message: string
  }
}

export type IpLookupResponse = IpLookupSuccessResponse | IpLookupFailureResponse

export interface RequestState<T> {
  loading: boolean
  error: string | null
  data: T | null
}