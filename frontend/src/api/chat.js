import api from './axios'

export const chatAPI = {
  listSessions:   (params)         => api.get('/api/chat/sessions/', { params }),
  createSession:  (data)           => api.post('/api/chat/sessions/', data),
  getSession:     (id)             => api.get(`/api/chat/sessions/${id}/`),
  updateSession:  (id, data)       => api.patch(`/api/chat/sessions/${id}/`, data),
  deleteSession:  (id)             => api.delete(`/api/chat/sessions/${id}/`),
  // `config` lets a request be cancelled mid-flight (see the Stop button).
  sendMessage:    (id, data, config) => api.post(`/api/chat/sessions/${id}/message/`, data, config),
  exportPDF:      (id)             => api.get(`/api/chat/sessions/${id}/export/`, { responseType: 'blob' }),
  search:         (params)         => api.get('/api/chat/search/', { params }),
  getConfig:      ()               => api.get('/api/chat/config/'),

  feedback:       (messageId, data) => api.post(`/api/chat/messages/${messageId}/feedback/`, data),
  getFeedback:    (messageId)       => api.get(`/api/chat/messages/${messageId}/feedback/`),
}

/**
 * Stream an answer over Server-Sent Events.
 *
 * fetch + ReadableStream rather than EventSource, because EventSource cannot
 * set an Authorization header — it only sends cookies — and this API
 * authenticates with a bearer token. fetch can, at the cost of parsing the SSE
 * frames here instead of getting them for free.
 *
 * `onEvent` is called with ({ type, ...payload }) for every frame:
 *   sources   citations, sent BEFORE the first token so the UI can render
 *             Sources immediately instead of the layout jumping at the end
 *   token     one fragment of the answer, to append
 *   security  a document contains what looks like an embedded instruction
 *   done      message_id (needed to attach feedback), timings, model
 *   error     generation failed; nothing further will arrive
 *
 * Returns an abort function, so a user navigating away or hitting Stop closes
 * the connection instead of leaving it streaming into nothing.
 */
export function streamMessage(sessionId, question, onEvent) {
  const controller = new AbortController()
  const base = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

  ;(async () => {
    try {
      const response = await fetch(`${base}/api/chat/sessions/${sessionId}/stream/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('access_token')}`,
        },
        body: JSON.stringify({ question }),
        signal: controller.signal,
      })

      if (!response.ok) {
        // Validation and ownership failures still arrive as ordinary JSON —
        // they happen before the stream starts, which is the whole reason the
        // view validates up front.
        const problem = await response.json().catch(() => ({}))
        onEvent({ type: 'error', message: problem.message || 'Request failed.' })
        return
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      for (;;) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        // Frames are separated by a blank line. Anything after the last one is
        // a partial frame and stays in the buffer until the rest arrives —
        // parsing it early is how a streamed answer loses characters.
        const frames = buffer.split('\n\n')
        buffer = frames.pop() || ''

        for (const frame of frames) {
          let type = 'message'
          const dataLines = []
          for (const line of frame.split('\n')) {
            if (line.startsWith('event: ')) type = line.slice(7).trim()
            else if (line.startsWith('data: ')) dataLines.push(line.slice(6))
            // ':' comment lines are keep-alives; ignored.
          }
          if (!dataLines.length) continue
          try {
            onEvent({ type, ...JSON.parse(dataLines.join('\n')) })
          } catch {
            // A frame we cannot parse must not kill the stream.
          }
        }
      }
    } catch (error) {
      if (error.name !== 'AbortError') {
        onEvent({ type: 'error', message: 'The connection was interrupted.' })
      }
    }
  })()

  return () => controller.abort()
}
