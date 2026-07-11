import api from './api'

const HISTORY_KEY = 'insightai-upload-history'

/**
 * Upload a PDF to the backend, reporting real byte-level progress.
 * @param {File} file
 * @param {(percent: number) => void} [onProgress]
 * @returns {Promise<{document_id: string, original_filename: string, stored_filename: string, file_size: number, upload_timestamp: string, status: string}>}
 */
export async function uploadDocument(file, onProgress) {
  const formData = new FormData()
  formData.append('file', file)

  const { data } = await api.post('/upload', formData, {
    timeout: 60000,
    onUploadProgress: (event) => {
      if (!onProgress || !event.total) return
      onProgress(Math.round((event.loaded / event.total) * 100))
    },
  })
  return data
}

/**
 * The backend doesn't yet expose a document list/delete API (that lives
 * entirely server-side against the vector store), so upload history is
 * tracked client-side from real, successful uploads. This is real data
 * about what this browser has uploaded, not mock data.
 */
export function getUploadHistory() {
  try {
    const raw = window.localStorage.getItem(HISTORY_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

export function addToUploadHistory(document) {
  const history = [document, ...getUploadHistory()]
  window.localStorage.setItem(HISTORY_KEY, JSON.stringify(history))
  return history
}

export function removeFromUploadHistory(documentId) {
  const history = getUploadHistory().filter((doc) => doc.document_id !== documentId)
  window.localStorage.setItem(HISTORY_KEY, JSON.stringify(history))
  return history
}
