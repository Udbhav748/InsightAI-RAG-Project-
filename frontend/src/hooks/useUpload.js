import { useCallback, useState } from 'react'
import { addToUploadHistory, uploadDocument } from '../services/documentService'
import getErrorMessage from '../utils/errorMessage'
import useToast from './useToast'

export default function useUpload() {
  const [file, setFile] = useState(null)
  const [progress, setProgress] = useState(0)
  const [status, setStatus] = useState('idle') // idle | uploading | success | error
  const [errorMessage, setErrorMessage] = useState('')
  const { showToast } = useToast()

  const selectFile = useCallback((selected) => {
    setFile(selected)
    setStatus('idle')
    setProgress(0)
    setErrorMessage('')
  }, [])

  const reset = useCallback(() => {
    setFile(null)
    setStatus('idle')
    setProgress(0)
    setErrorMessage('')
  }, [])

  const startUpload = useCallback(async () => {
    if (!file) return
    setStatus('uploading')
    setProgress(0)

    try {
      const result = await uploadDocument(file, setProgress)
      setStatus('success')
      // DocumentProcessingResponse carries no timestamp — stamp one
      // locally so Documents can sort/display by upload time.
      addToUploadHistory({ ...result, uploaded_at: new Date().toISOString() })
      // pages_ocred > 0 means some pages had no text layer (scanned/image
      // pages) and were recovered via OCR — worth surfacing, since OCR'd
      // text is lower-fidelity than the document's real text.
      const ocrNote = result.pages_ocred > 0 ? ` (${result.pages_ocred} page(s) recovered via OCR)` : ''
      showToast(`${result.original_filename} uploaded successfully${ocrNote}.`, 'success')
    } catch (error) {
      const message = getErrorMessage(error, 'Upload failed. Please try again.')
      setStatus('error')
      setErrorMessage(message)
      showToast(message, 'error')
    }
  }, [file, showToast])

  return { file, progress, status, errorMessage, selectFile, reset, startUpload }
}
