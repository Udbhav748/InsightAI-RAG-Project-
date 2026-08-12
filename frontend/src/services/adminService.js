import api from './api'

/**
 * Admin-only usage analytics (GET /admin/usage-summary) — daily request
 * counts and average latencies, newest first. The backend 403s this for
 * any non-admin role, so callers should gate the UI on user.role === 'admin'.
 * @returns {Promise<{rows: {day: string, request_count: number, avg_latency_ms: number}[]}>}
 */
export async function getUsageSummary() {
  const { data } = await api.get('/admin/usage-summary')
  return data
}
