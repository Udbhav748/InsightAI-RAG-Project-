import api, { AUTH_TOKEN_KEY } from './api'

// Mirrors api.js's own fallback/env resolution — fetch-based SSE can't
// reuse the axios instance directly (axios has no streaming-body request
// mode), so the base URL is resolved the same way here rather than
// reaching into api.defaults' internal shape. The auth token is read
// fresh per call (same reasoning as api.js's request interceptor: a
// login/logout between calls must take effect immediately).
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'

/**
 * Send a chat query to the RAG pipeline.
 * @param {string} query
 * @param {{ topK?: number, minScore?: number, history?: {role: string, content: string}[], sessionId?: string }} [options]
 * @returns {Promise<{answer: string, retrieved_chunks: object[], sources: {document_id: string, chunk_id: string, excerpt: string}[], processing_time: number, tool_used: string, steps_taken: number, session_id: string}>}
 */
function buildChatPayload(query, options) {
  const payload = { query }
  if (options.topK != null) payload.top_k = options.topK
  if (options.minScore != null) payload.min_score = options.minScore
  if (options.history?.length) payload.history = options.history
  if (options.sessionId) payload.session_id = options.sessionId
  if (options.persona) payload.persona = options.persona
  if (options.documentIds?.length) payload.document_ids = options.documentIds
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
 * @param {{ topK?: number, minScore?: number, history?: {role: string, content: string}[], sessionId?: string }} [options]
 * @param {{
 *   onTrace?: (stage: string, detail: object) => void,
 *   onChunk?: (text: string) => void,
 *   onDone?: (payload: object) => void,
 *   onError?: (detail: { error_type: string, message: string, status_code: number }) => void,
 * }} [callbacks]
 */
export async function streamChatMessage(query, options = {}, callbacks = {}) {
  const { onTrace, onChunk, onDone, onError } = callbacks

  const token = window.localStorage.getItem(AUTH_TOKEN_KEY)
  const response = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
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

/**
 * Delete the server-side chat session by id (DELETE /chat/sessions/{id}).
 * @param {string} sessionId
 * @returns {Promise<{status: string, session_id: string}>}
 */
export async function deleteChatSession(sessionId) {
  const { data } = await api.delete(`/chat/sessions/${encodeURIComponent(sessionId)}`)
  return data
}

/**
 * List the caller's own past conversations (title, timestamps),
 * newest-accessed first — the history sidebar's data source.
 * @returns {Promise<{sessions: {session_id: string, title: string|null, created_at: string|null, last_accessed_at: string|null}[], total: number}>}
 */
export async function listSessions() {
  const { data } = await api.get('/chat/sessions')
  return data
}

/**
 * Full turn history for one session — used to resume a past
 * conversation from the history list.
 * @param {string} sessionId
 * @returns {Promise<{session_id: string, turns: {role: string, content: string}[]}>}
 */
export async function getSession(sessionId) {
  const { data } = await api.get(`/chat/sessions/${encodeURIComponent(sessionId)}`)
  return data
}
