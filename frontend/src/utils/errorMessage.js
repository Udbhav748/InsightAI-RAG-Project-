/**
 * Extract a human-readable message from an axios error, matching the
 * backend's error shapes: {"detail": "message"} from AppError, or
 * {"detail": [{"msg": "..."}]} from FastAPI's request validation.
 */
export default function getErrorMessage(error, fallback = 'Something went wrong. Please try again.') {
  const detail = error?.response?.data?.detail

  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg
  if (error?.code === 'ECONNABORTED') return 'The request timed out. Please try again.'
  if (error?.message === 'Network Error') return 'Unable to reach the server. Please check your connection.'

  return fallback
}
