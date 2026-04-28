import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { BackgroundDecor } from './components/BackgroundDecor'
import { TopNav, type HealthIndicatorTone } from './components/TopNav'
import { fetchHealth, fetchPing, fetchTraceroute } from './lib/api'
import { normalizeHostInput, toErrorMessage, validateHostInput } from './lib/format'
import type { HealthResponse, PingResponse, RequestState, TracerouteResponse } from './lib/types'
import { ApiExamples } from './sections/ApiExamples'
import { Hero } from './sections/Hero'
import { Tools } from './sections/Tools'

function emptyState<T>(): RequestState<T> {
  return {
    loading: false,
    error: null,
    data: null,
  }
}

function App() {
  const [healthState, setHealthState] = useState<RequestState<HealthResponse>>({
    loading: true,
    error: null,
    data: null,
  })
  const [pingHost, setPingHost] = useState('1.1.1.1')
  const [pingValidationError, setPingValidationError] = useState<string | null>(null)
  const [pingState, setPingState] = useState<RequestState<PingResponse>>(emptyState)
  const [tracerouteHost, setTracerouteHost] = useState('8.8.8.8')
  const [tracerouteValidationError, setTracerouteValidationError] = useState<string | null>(null)
  const [tracerouteState, setTracerouteState] = useState<RequestState<TracerouteResponse>>(emptyState)

  const healthAbortRef = useRef<AbortController | null>(null)
  const pingAbortRef = useRef<AbortController | null>(null)
  const tracerouteAbortRef = useRef<AbortController | null>(null)

  const runPing = useCallback(async () => {
    const host = normalizeHostInput(pingHost)
    setPingHost(host)
    const validationError = validateHostInput(host)
    setPingValidationError(validationError)

    if (validationError) {
      return
    }

    pingAbortRef.current?.abort()
    const controller = new AbortController()
    pingAbortRef.current = controller

    setPingState({ loading: true, error: null, data: null })

    try {
      const result = await fetchPing(host, controller.signal)
      if (controller.signal.aborted) {
        return
      }
      setPingState({ loading: false, error: null, data: result })
    } catch (error) {
      if (controller.signal.aborted) {
        return
      }
      setPingState({ loading: false, error: toErrorMessage(error), data: null })
    }
  }, [pingHost])

  const runTraceroute = useCallback(async () => {
    const host = normalizeHostInput(tracerouteHost)
    setTracerouteHost(host)
    const validationError = validateHostInput(host)
    setTracerouteValidationError(validationError)

    if (validationError) {
      return
    }

    tracerouteAbortRef.current?.abort()
    const controller = new AbortController()
    tracerouteAbortRef.current = controller

    setTracerouteState({ loading: true, error: null, data: null })

    try {
      const result = await fetchTraceroute(host, controller.signal)
      if (controller.signal.aborted) {
        return
      }
      setTracerouteState({ loading: false, error: null, data: result })
    } catch (error) {
      if (controller.signal.aborted) {
        return
      }
      setTracerouteState({ loading: false, error: toErrorMessage(error), data: null })
    }
  }, [tracerouteHost])

  useEffect(() => {
    healthAbortRef.current?.abort()
    const controller = new AbortController()
    healthAbortRef.current = controller

    const bootstrapHealth = async () => {
      try {
        const result = await fetchHealth(controller.signal)
        if (controller.signal.aborted) {
          return
        }
        setHealthState({ loading: false, error: null, data: result })
      } catch (error) {
        if (controller.signal.aborted) {
          return
        }
        setHealthState({ loading: false, error: toErrorMessage(error), data: null })
      }
    }

    void bootstrapHealth()

    return () => {
      controller.abort()
      pingAbortRef.current?.abort()
      tracerouteAbortRef.current?.abort()
    }
  }, [])

  const focusPingInput = useCallback(() => {
    document.getElementById('ping-host')?.focus()
  }, [])

  const scrollToExamples = useCallback(() => {
    document.getElementById('api-examples')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [])

  const topNavHealth = useMemo<{ label: string; tone: HealthIndicatorTone }>(() => {
    if (healthState.loading) {
      return { label: 'Checking API', tone: 'pending' }
    }

    if (healthState.error) {
      return { label: 'API error', tone: 'error' }
    }

    if (healthState.data?.status.toLowerCase() === 'ok') {
      return { label: 'API online', tone: 'success' }
    }

    return { label: 'API degraded', tone: 'warning' }
  }, [healthState])

  return (
    <div className="min-h-screen bg-bgpx-black text-bgpx-ink">
      <BackgroundDecor />
      <TopNav healthLabel={topNavHealth.label} healthTone={topNavHealth.tone} onFocusPrimaryInput={focusPingInput} />

      <div className="mx-auto max-w-7xl px-4 py-8">
        <main className="min-w-0 space-y-10">
          <Hero onRunCheck={focusPingInput} onViewExamples={scrollToExamples} />
          <Tools
            pingHost={pingHost}
            pingValidationError={pingValidationError}
            pingState={pingState}
            onPingHostChange={setPingHost}
            onRunPing={runPing}
            tracerouteHost={tracerouteHost}
            tracerouteValidationError={tracerouteValidationError}
            tracerouteState={tracerouteState}
            onTracerouteHostChange={setTracerouteHost}
            onRunTraceroute={runTraceroute}
          />
          <ApiExamples />
        </main>
      </div>
    </div>
  )
}

export default App
