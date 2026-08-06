import api from './api'

// Mirrors api.js's own fallback/env resolution — fetch-based SSE can't
// reuse the axios instance directly (axios has no streaming-body request
// mode), so the base URL and API key are resolved the same way here
// rather than reaching into api.defaults' internal header shape.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
const API_KEY = import.meta.env.VITE_API_KEY

/**
 * Send a chat query to the RAG pipeline.
 * @param {string} query
 * @param {{ topK?: number, minScore?: number, history?: {role: string, content: string}[] }} [options]
 * @returns {Promise<{answer: string, retrieved_chunks: object[], sources: {document_id: string, chunk_id: string, excerpt: string}[], processing_time: number, tool_used: string, steps_taken: number}>}
 */
function buildChatPayload(query, options) {
  const payload = { query }
  if (options.topK != null) payload.top_k = options.topK
  if (options.minScore != null) payload.min_score = options.minScore
  if (options.history?.length) payload.history = options.history
  return payload
}

export async function sendChatMessage(query, options = {}) {
  // Generation can be slow on a cold embedding-model / LLM call, so this
  // request gets a longer timeout than the shared api instance default.
  const { data } = await api.post('/chat', buildChatPayload(query, options), { timeout: 60000 })
  return data
}

/**
 * Send a chat query to POST /chat/stream and consume the Server-Sent
 * Events response as it arrives.
 *
 * Uses fetch + a manually-parsed ReadableStream rather than the browser's
 * EventSource: EventSource only supports GET with no custom headers, and
 * this endpoint needs POST (a query body) plus the X-API-Key header.
 *
 * @param {string} query
 * @param {{ topK?: number, minScore?: number, history?: {role: string, content: string}[] }} [options]
 * @param {{
 *   onTrace?: (stage: string, detail: object) => void,
 *   onChunk?: (text: string) => void,
 *   onDone?: (payload: object) => void,
 *   onError?: (detail: { error_type: string, message: string, status_code: number }) => void,
 * }} [callbacks]
 */
export async function streamChatMessage(query, options = {}, callbacks = {}) {
  const { onTrace, onChunk, onDone, onError } = callbacks

  const response = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': API_KEY,
    },
    body: JSON.stringify(buildChatPayload(query, options)),
  })

  if (!response.ok || !response.body) {
    const error = new Error(`Request failed with status ${response.status}`)
    error.response = { status: response.status, data: await response.json().catch(() => null) }
    throw error
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // SSE frames are separated by a blank line; a single read() can
    // contain zero, one, or several complete frames, and a frame can also
    // be split across reads — buffer and only consume complete frames.
    let boundary = buffer.indexOf('\n\n')
    while (boundary !== -1) {
      const rawEvent = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)

      const data = rawEvent
        .split('\n')
        .filter((line) => line.startsWith('data: '))
        .map((line) => line.slice('data: '.length))
        .join('\n')

      if (data) {
        const event = JSON.parse(data)
        if (event.type === 'trace') onTrace?.(event.stage, event.detail)
        else if (event.type === 'answer_chunk') onChunk?.(event.text)
        else if (event.type === 'error') onError?.(event.detail)
        else if (event.type === 'done') onDone?.(event.payload)
      }

      boundary = buffer.indexOf('\n\n')
    }
  }
}
