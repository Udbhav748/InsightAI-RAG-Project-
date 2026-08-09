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
