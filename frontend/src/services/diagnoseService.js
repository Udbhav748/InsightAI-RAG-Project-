import api from './api'

/**
 * Diagnose a plant leaf photo via POST /chat/diagnose.
 *
 * The backend sends the image to the LeafSense vision service, then runs the
 * predicted disease through the same corrective-RAG loop as /chat — so the
 * response is a full ChatResponse with answer, sources, and a diagnosis
 * block describing the vision prediction itself.
 *
 * @param {File} image An image file (from camera capture or file picker).
 * @param {{ query?: string, sessionId?: string, confirmWebSearch?: boolean }} [options]
 * @returns {Promise<{answer: string, retrieved_chunks: object[], sources: object[], processing_time: number, tool_used: string, steps_taken: number, diagnosis: {raw_class: string, crop: string, disease: string, confidence: number, low_confidence: boolean} | null, session_id: string}>}
 */
export async function diagnoseLeaf(image, options = {}) {
  const formData = new FormData()
  formData.append('image', image)
  if (options.query?.trim()) formData.append('query', options.query.trim())
  if (options.sessionId) formData.append('session_id', options.sessionId)
  if (options.confirmWebSearch) formData.append('confirm_web_search', String(options.confirmWebSearch))

  // Vision inference + retrieval + generation can be slow, so this gets the
  // same longer timeout as /chat rather than the shared api instance default.
  const { data } = await api.post('/chat/diagnose', formData, { timeout: 60000 })
  return data
}

/**
 * Check if the LeafSense vision service (port 8001) or vision pipeline is reachable.
 * @returns {Promise<{online: boolean, port: number, url: string, message?: string}>}
 */
export async function checkLeafSenseHealth() {
  try {
    const { data } = await api.get('/health/vision', { timeout: 3000 })
    return {
      online: Boolean(data?.online || data?.has_gemini_fallback),
      port: 8001,
      url: data?.url || 'http://localhost:8001',
      status: data?.status || 'ok',
      hasGeminiFallback: Boolean(data?.has_gemini_fallback),
    }
  } catch {
    // Direct browser probe fallback
    try {
      const direct = await fetch('http://localhost:8001/model-info', { method: 'GET', signal: AbortSignal.timeout(2000) })
      if (direct.ok) {
        return { online: true, port: 8001, url: 'http://localhost:8001', status: 'online' }
      }
    } catch {
      // offline
    }
    return {
      online: false,
      port: 8001,
      url: 'http://localhost:8001',
      message: 'LeafSense service offline on port 8001',
    }
  }
}
