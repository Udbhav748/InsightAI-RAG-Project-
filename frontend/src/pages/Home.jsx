import { useState, useEffect } from 'react'
import api from '../services/api'

export default function Home() {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.get('/health')
      .then(res => setStatus(res.data.status))
      .catch(() => setError('Unable to reach backend.'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="text-center py-20">
      <h1 className="text-4xl font-bold text-gray-900 mb-4">InsightAI RAG</h1>
      <p className="text-gray-500 text-lg max-w-md mx-auto mb-8">
        Upload PDF documents and ask questions in natural language.
      </p>

      <div className="inline-flex items-center gap-2 text-sm px-4 py-2 rounded-full bg-white border border-gray-200 shadow-sm">
        {loading && <span className="text-gray-400">Checking backend…</span>}
        {error && (
          <>
            <span className="h-2 w-2 rounded-full bg-red-400" />
            <span className="text-red-500">{error}</span>
          </>
        )}
        {status && (
          <>
            <span className="h-2 w-2 rounded-full bg-green-500" />
            <span className="text-gray-600">Backend connected</span>
          </>
        )}
      </div>
    </div>
  )
}
