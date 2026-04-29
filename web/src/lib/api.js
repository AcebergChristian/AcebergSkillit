async function fetchJson(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `HTTP ${response.status}`)
  }
  return response.json()
}

export function getOverview() {
  return fetchJson('/api/overview')
}

export function getRuntime() {
  return fetchJson('/api/runtime')
}

export function getSessions() {
  return fetchJson('/api/sessions')
}

export function getSession(sessionId) {
  return fetchJson(`/api/sessions/${sessionId}`)
}

export function getSkills() {
  return fetchJson('/api/skills')
}

export function runRequirement(body) {
  return fetchJson('/api/run', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function chat(body) {
  return fetchJson('/api/chat', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function runRequirementStream(body, handlers = {}) {
  const response = await fetch('/api/run/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok || !response.body) {
    const text = await response.text()
    throw new Error(text || `HTTP ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed) continue
      const message = JSON.parse(trimmed)
      if (message.type === 'event') handlers.onEvent?.(message.data)
      if (message.type === 'final') handlers.onFinal?.(message.data)
      if (message.type === 'error') handlers.onError?.(message.data)
    }
  }

  if (buffer.trim()) {
    const message = JSON.parse(buffer.trim())
    if (message.type === 'final') handlers.onFinal?.(message.data)
    if (message.type === 'error') handlers.onError?.(message.data)
  }
}

export async function chatStream(body, handlers = {}) {
  const response = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok || !response.body) {
    const text = await response.text()
    throw new Error(text || `HTTP ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed) continue
      const message = JSON.parse(trimmed)
      if (message.type === 'event') handlers.onEvent?.(message.data)
      if (message.type === 'final') handlers.onFinal?.(message.data)
      if (message.type === 'error') handlers.onError?.(message.data)
    }
  }

  if (buffer.trim()) {
    const message = JSON.parse(buffer.trim())
    if (message.type === 'final') handlers.onFinal?.(message.data)
    if (message.type === 'error') handlers.onError?.(message.data)
  }
}
