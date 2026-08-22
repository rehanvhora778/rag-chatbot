/**
 * Tests for the SSE parser in streamMessage.
 *
 * This is the piece most worth testing on the frontend: it hand-parses a wire
 * format, and every one of its failure modes is silent. A frame split across
 * two network chunks, a payload containing a newline, a keep-alive comment —
 * each produces a subtly wrong answer in the UI with no error anywhere.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { streamMessage } from './chat'

/** A fetch whose body streams the given chunks, exactly as split. */
function mockFetchStreaming(chunks, { ok = true, status = 200 } = {}) {
  const encoder = new TextEncoder()
  let index = 0

  return vi.fn().mockResolvedValue({
    ok,
    status,
    json: async () => ({ message: 'nope' }),
    body: {
      getReader: () => ({
        read: async () =>
          index < chunks.length
            ? { done: false, value: encoder.encode(chunks[index++]) }
            : { done: true, value: undefined },
      }),
    },
  })
}

const frame = (event, data) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`

/** Wait for the async reader loop to drain. */
const settle = () => new Promise(resolve => setTimeout(resolve, 0))

describe('streamMessage', () => {
  beforeEach(() => {
    localStorage.setItem('access_token', 'test-token')
  })
  afterEach(() => {
    localStorage.clear()
  })

  it('emits each frame as a typed event', async () => {
    globalThis.fetch = mockFetchStreaming([
      frame('sources', { citations: [{ page_number: 2 }], retrieval_ms: 12 }),
      frame('token', { text: 'Refunds ' }),
      frame('token', { text: 'take 30 days.' }),
      frame('done', { message_id: 'abc', refused: false }),
    ])

    const events = []
    streamMessage('s1', 'q', e => events.push(e))
    await settle()

    expect(events.map(e => e.type)).toEqual(['sources', 'token', 'token', 'done'])
    expect(events[0].citations[0].page_number).toBe(2)
    expect(events[3].message_id).toBe('abc')
  })

  it('reassembles a frame split across two network chunks', async () => {
    // The failure this guards: parsing the buffer eagerly drops the half-frame
    // and the answer silently loses characters.
    const whole = frame('token', { text: 'hello world' })
    const cut = Math.floor(whole.length / 2)

    globalThis.fetch = mockFetchStreaming([whole.slice(0, cut), whole.slice(cut)])

    const events = []
    streamMessage('s1', 'q', e => events.push(e))
    await settle()

    expect(events).toHaveLength(1)
    expect(events[0].text).toBe('hello world')
  })

  it('handles several frames arriving in one chunk', async () => {
    globalThis.fetch = mockFetchStreaming([
      frame('token', { text: 'a' }) + frame('token', { text: 'b' }) + frame('token', { text: 'c' }),
    ])

    const events = []
    streamMessage('s1', 'q', e => events.push(e))
    await settle()

    expect(events.map(e => e.text)).toEqual(['a', 'b', 'c'])
  })

  it('preserves newlines inside a payload', async () => {
    // The server JSON-encodes for exactly this reason. If the client split on
    // raw newlines instead, a markdown answer would be truncated at its first
    // paragraph break.
    const text = '## Heading\n\n- one\n- two'
    globalThis.fetch = mockFetchStreaming([frame('token', { text })])

    const events = []
    streamMessage('s1', 'q', e => events.push(e))
    await settle()

    expect(events[0].text).toBe(text)
  })

  it('ignores keep-alive comment lines', async () => {
    globalThis.fetch = mockFetchStreaming([
      ': keep-alive\n\n',
      frame('token', { text: 'x' }),
    ])

    const events = []
    streamMessage('s1', 'q', e => events.push(e))
    await settle()

    expect(events).toHaveLength(1)
    expect(events[0].type).toBe('token')
  })

  it('survives a frame it cannot parse', async () => {
    // One malformed frame must not end the stream — the rest of the answer is
    // still coming.
    globalThis.fetch = mockFetchStreaming([
      'event: token\ndata: {not json\n\n',
      frame('token', { text: 'recovered' }),
    ])

    const events = []
    streamMessage('s1', 'q', e => events.push(e))
    await settle()

    expect(events.map(e => e.text)).toEqual(['recovered'])
  })

  it('reports a rejected request as an error event', async () => {
    // Validation and ownership failures happen before the stream starts and
    // arrive as ordinary JSON, which is why the view validates up front.
    globalThis.fetch = mockFetchStreaming([], { ok: false, status: 404 })

    const events = []
    streamMessage('s1', 'q', e => events.push(e))
    await settle()

    expect(events).toEqual([{ type: 'error', message: 'nope' }])
  })

  it('sends the bearer token', async () => {
    const fetchMock = mockFetchStreaming([])
    globalThis.fetch = fetchMock

    streamMessage('s1', 'What is the refund window?', () => {})
    await settle()

    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toContain('/api/chat/sessions/s1/stream/')
    expect(options.headers.Authorization).toBe('Bearer test-token')
    expect(JSON.parse(options.body).question).toBe('What is the refund window?')
  })

  it('returns an abort function that does not surface as an error', async () => {
    // Pressing Stop or navigating away is a user action, not a failure.
    globalThis.fetch = vi.fn().mockRejectedValue(
      Object.assign(new Error('aborted'), { name: 'AbortError' }),
    )

    const events = []
    const abort = streamMessage('s1', 'q', e => events.push(e))
    abort()
    await settle()

    expect(typeof abort).toBe('function')
    expect(events).toEqual([])
  })
})
