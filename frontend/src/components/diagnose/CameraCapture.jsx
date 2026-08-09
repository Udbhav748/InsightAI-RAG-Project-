import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { Camera, CameraOff, ImagePlus, RefreshCw } from 'lucide-react'
import Button from '../ui/Button'

/**
 * Live camera capture with a file-upload fallback.
 *
 * On mount it requests a stream from getUserMedia (back camera preferred for
 * a leaf photo). When the user presses "Capture", the current video frame is
 * drawn to a hidden canvas and converted to a File via toBlob. If the camera
 * is unavailable or permission is denied, a file picker fallback is shown so
 * the feature still works from a phone's existing photos.
 */
export default function CameraCapture({ onCapture, disabled }) {
  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const streamRef = useRef(null)
  const facingModeRef = useRef('environment')
  const fileInputRef = useRef(null)
  const [cameraState, setCameraState] = useState('starting') // starting | active | error
  const [cameraError, setCameraError] = useState('')
  const [switching, setSwitching] = useState(false)

  const stopStream = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
  }

  useEffect(() => {
    let cancelled = false

    async function startCamera() {
      setCameraState('starting')
      if (!navigator.mediaDevices?.getUserMedia) {
        setCameraError('Camera is not supported in this browser. You can upload a photo instead.')
        setCameraState('error')
        return
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'environment' },
          audio: false,
        })
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop())
          return
        }
        streamRef.current = stream
        facingModeRef.current = 'environment'
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          await videoRef.current.play()
        }
        setCameraError('')
        setCameraState('active')
      } catch (error) {
        if (cancelled) return
        const message =
          error?.name === 'NotAllowedError'
            ? 'Camera permission was denied. Allow camera access, or upload a photo instead.'
            : 'Could not start the camera. You can upload a photo instead.'
        setCameraError(message)
        setCameraState('error')
      }
    }

    startCamera()
    return () => {
      cancelled = true
      stopStream()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const capture = async () => {
    const video = videoRef.current
    const canvas = canvasRef.current
    if (!video || !canvas) return
    canvas.width = video.videoWidth || 1280
    canvas.height = video.videoHeight || 720
    canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.92))
    if (!blob) return
    const file = new File([blob], `leaf-capture-${Date.now()}.jpg`, { type: 'image/jpeg' })
    onCapture(file)
  }

  const switchCamera = async () => {
    setSwitching(true)
    stopStream()
    const nextMode = facingModeRef.current === 'environment' ? 'user' : 'environment'
    facingModeRef.current = nextMode
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: nextMode },
        audio: false,
      })
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play()
      }
      setCameraError('')
      setCameraState('active')
    } catch {
      facingModeRef.current = 'environment'
      setCameraError('Could not switch camera. You can upload a photo instead.')
      setCameraState('error')
    } finally {
      setSwitching(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="panel relative overflow-hidden rounded-panel bg-slate-950">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className={`h-72 w-full object-cover ${cameraState === 'active' ? '' : 'hidden'}`}
        />
        {cameraState !== 'active' && (
          <div className="flex h-72 flex-col items-center justify-center gap-3 px-6 text-center">
            <span className="flex h-12 w-12 items-center justify-center rounded-xl border border-border-light bg-white/5 text-ink-muted">
              <CameraOff size={20} strokeWidth={1.5} />
            </span>
            <p className="max-w-sm text-sm text-slate-400 dark:text-ink-muted">
              {cameraState === 'starting' ? 'Starting camera...' : cameraError || 'Camera unavailable.'}
            </p>
          </div>
        )}
        <canvas ref={canvasRef} className="hidden" />
      </div>

      <div className="flex flex-wrap items-center justify-center gap-3">
        <Button
          variant="primary"
          icon={Camera}
          disabled={disabled || cameraState !== 'active'}
          onClick={capture}
        >
          Capture photo
        </Button>
        <Button
          variant="secondary"
          icon={RefreshCw}
          disabled={disabled || cameraState !== 'active' || switching}
          loading={switching}
          onClick={switchCamera}
        >
          Switch camera
        </Button>
        <Button
          variant="ghost"
          icon={ImagePlus}
          disabled={disabled}
          onClick={() => fileInputRef.current?.click()}
        >
          Upload a photo
        </Button>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        disabled={disabled}
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) onCapture(file)
          event.target.value = ''
        }}
      />

      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="text-center text-xs text-slate-400 dark:text-ink-muted"
      >
        Hold the leaf flat, in good light, filling most of the frame.
      </motion.p>
    </div>
  )
}
