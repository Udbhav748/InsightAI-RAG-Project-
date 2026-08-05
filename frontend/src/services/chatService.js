import api from './api'

/**
 * Send a chat query to the RAG pipeline.
 * @param {string} query
 * @param {{ topK?: number, minScore?: number, history?: {role: string, content: string}[] }} [options]
 * @returns {Promise<{answer: string, retrieved_chunks: object[], sources: string[], processing_time: number, tool_used: string, steps_taken: number}>}
 */
export async function sendChatMessage(query, options = {}) {
  const payload = { query }
  if (options.topK != null) payload.top_k = options.topK
  if (options.minScore != null) payload.min_score = options.minScore
  if (options.history?.length) payload.history = options.history

  // Generation can be slow on a cold embedding-model / LLM call, so this
  // request gets a longer timeout than the shared api instance default.
  const { data } = await api.post('/chat', payload, { timeout: 60000 })
  return data
}
