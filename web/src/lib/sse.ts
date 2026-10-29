import { getCsrfToken } from './api'

export interface SSEEvent {
  type?: string
  [key: string]: any
}

export function parseSSEChunk(chunk: string, residual: string): { events: SSEEvent[]; residual: string } {
  const combined = residual + chunk
  const events: SSEEvent[] = []
  const blocks = combined.split('\n\n')
  const leftover = blocks.pop() ?? ''
  for (const block of blocks) {
    if (!block.trim()) continue
    let data = ''
    for (const line of block.split('\n')) {
      if (line.startsWith('data:')) {
        data += line.slice(5)
        if (data.startsWith(' ')) data = data.slice(1)
      }
    }
    if (data) {
      try { events.push(JSON.parse(data)) } catch { /* skip */ }
    }
  }
  return { events, residual: leftover }
}

export async function streamSSE(
  url: string,
  body: any,
  onEvent: (ev: SSEEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const csrf = getCsrfToken()
  if (csrf) headers['X-CSRF-Token'] = csrf
  const res = await fetch(url, { method: 'POST', credentials: 'include', headers, body: JSON.stringify(body), signal })
  if (!res.ok) {
    let msg = `Error ${res.status}`
    try { const j = await res.json(); msg = j.detail || msg } catch {}
    onEvent({ type: 'error', message: msg })
    return
  }
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let residual = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    const chunk = decoder.decode(value, { stream: true })
    const { events, residual: nextResidual } = parseSSEChunk(chunk, residual)
    residual = nextResidual
    for (const ev of events) onEvent(ev)
  }
  if (residual.trim()) {
    const { events } = parseSSEChunk('', residual + '\n\n')
    for (const ev of events) onEvent(ev)
  }
}