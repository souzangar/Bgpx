export function formatJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    if (value instanceof Error) {
      return value.message || value.name
    }

    if (typeof value === 'string') {
      return value
    }

    return 'Unable to format value as JSON.'
  }
}

export function formatMs(value: number | null | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '—'
  }

  const precision = value >= 100 ? 0 : 2
  return `${value.toFixed(precision)} ms`
}

export function formatPercent(value: number | null | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '—'
  }

  return `${value.toFixed(1)}%`
}

export function normalizeHostInput(host: string): string {
  return host.trim()
}

export function validateHostInput(host: string): string | null {
  const trimmed = host.trim()

  if (!trimmed) {
    return 'Target host is required.'
  }

  if (trimmed.length > 253) {
    return 'Host value is too long (maximum 253 characters).'
  }

  return null
}

export function toErrorMessage(error: unknown): string {
  if (error instanceof DOMException && error.name === 'AbortError') {
    return 'Request was canceled.'
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message.trim()
  }

  return 'Request failed. Please try again.'
}