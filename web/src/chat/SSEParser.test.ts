import { parseSSEChunk } from '../lib/sse'

describe('parseSSEChunk', () => {
  it('splits chunks across events', () => {
    const { events, residual } = parseSSEChunk('data: {"type":"token","text":"hi"}\n\n', '')
    expect(events).toHaveLength(1)
    expect(events[0].type).toBe('token')
    expect(events[0].text).toBe('hi')
    expect(residual).toBe('')
  })

  it('handles multi-byte characters', () => {
    const { events } = parseSSEChunk(`data: {"type":"token","text":"café"}\n\n`, '')
    expect(events[0].text).toBe('café')
  })

  it('handles split chunks', () => {
    const conv = 'data: {"type":"token","text":"hello"}\n\n'
    const mid = Math.floor(conv.length / 2)
    const first = parseSSEChunk(conv.slice(0, mid), '')
    const second = parseSSEChunk(conv.slice(mid), first.residual)
    expect(first.events).toHaveLength(0)
    expect(second.events).toHaveLength(1)
    expect(second.events[0].text).toBe('hello')
  })

  it('parses error events', () => {
    const chunk = 'data: {"type":"error","message":"Daily limit reached"}\n\n'
    const { events } = parseSSEChunk(chunk, '')
    expect(events[0].type).toBe('error')
  })
})
