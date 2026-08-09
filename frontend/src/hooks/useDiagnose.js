import { useCallback, useEffect, useRef, useState } from 'react'
import { diagnoseLeaf } from '../services/diagnoseService'
import getErrorMessage from '../utils/errorMessage'
import useToast from './useToast'

const MAX_IMAGE_SIZE_MB = 20

export default function useDiagnose() {
  const [image, setImage] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('idle') // idle | preview | analyzing | success | error
  const [result, setResult] = useState(null)
  const [errorMessage, setErrorMessage] = useState('')
  const previewUrlRef = useRef(null)
  const { showToast } = useToast()

  const revokePreview = useCallback(() => {
    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current)
      previewUrlRef.current = null
    }
  }, [])

  useEffect(() => revokePreview, [revokePreview])

  const selectImage = useCallback(
    (file) => {
      const isImage = (file.type || '').startsWith('image/')
      if (!isImage) {
        showToast('Please choose an image file (JPG, PNG, WEBP, ...).', 'error')
        return
      }
      if (file.size > MAX_IMAGE_SIZE_MB * 1024 * 1024) {
        showToast(`Image exceeds the ${MAX_IMAGE_SIZE_MB} MB size limit.`, 'error')
        return
      }
      revokePreview()
      const url = URL.createObjectURL(file)
      previewUrlRef.current = url
      setImage(file)
      setPreviewUrl(url)
      setResult(null)
      setErrorMessage('')
      setStatus('preview')
    },
    [revokePreview, showToast]
  )

  const setQueryText = useCallback((text) => setQuery(text), [])

  const analyze = useCallback(async () => {
    if (!image || status === 'analyzing') return
    setStatus('analyzing')
    setErrorMessage('')
    try {
      const response = await diagnoseLeaf(image, { query })
      setResult(response)
      setStatus('success')
    } catch (error) {
      const message = getErrorMessage(error, 'Diagnosis failed. Please try again.')
      setErrorMessage(message)
      setStatus('error')
      showToast(message, 'error')
    }
  }, [image, query, status, showToast])

  const reset = useCallback(() => {
    revokePreview()
    setImage(null)
    setPreviewUrl(null)
    setQuery('')
    setResult(null)
    setErrorMessage('')
    setStatus('idle')
  }, [revokePreview])

  return {
    image,
    previewUrl,
    query,
    status,
    result,
    errorMessage,
    selectImage,
    setQueryText,
    analyze,
    reset,
  }
}
