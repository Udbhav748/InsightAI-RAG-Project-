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
      // text is lower-fidelity than the document's real text. Same
      // reasoning for the multi-modal counts below (all 0 when those
      // features are off, so this is a no-op note on a normal deployment).
      const notes = []
      if (result.pages_ocred > 0) notes.push(`${result.pages_ocred} page(s) recovered via OCR`)
      if (result.images_captioned > 0) notes.push(`${result.images_captioned} image(s) captioned`)
      if (result.total_tables > 0) notes.push(`${result.total_tables} table(s) extracted`)
      const note = notes.length > 0 ? ` (${notes.join(', ')})` : ''
      showToast(`${result.original_filename} uploaded successfully${note}.`, 'success')
    } catch (error) {
      const message = getErrorMessage(error, 'Upload failed. Please try again.')
      setStatus('error')
      setErrorMessage(message)
      showToast(message, 'error')
    }
  }, [file, showToast])

  return { file, progress, status, errorMessage, selectFile, reset, startUpload }
}
