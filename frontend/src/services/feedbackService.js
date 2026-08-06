import api from './api'

/**
 * Record a thumbs up/down (and optional comment) on a chat answer.
 * @param {string} messageId - The frontend's own id for the assistant message.
 * @param {'up'|'down'} rating
 * @param {string|null} [comment]
 * @returns {Promise<{status: string}>}
 */
export async function sendFeedback(messageId, rating, comment = null) {
  const { data } = await api.post('/chat/feedback', {
    message_id: messageId,
    rating,
    comment,
  })
  return data
}
