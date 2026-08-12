import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Leaf, RefreshCw, ScanLine } from 'lucide-react'
import Button from '../components/ui/Button'
import CameraCapture from '../components/diagnose/CameraCapture'
import DiagnosisResult from '../components/diagnose/DiagnosisResult'
import useDiagnose from '../hooks/useDiagnose'

const QUERY_MAX_HEIGHT = 200

export default function Diagnose() {
  const { image, previewUrl, query, status, result, errorMessage, selectImage, setQueryText, analyze, reset } =
    useDiagnose()
  const [showCamera, setShowCamera] = useState(true)
  const queryRef = useRef(null)

  useEffect(() => {
    const el = queryRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, QUERY_MAX_HEIGHT)}px`
  }, [query])

  const handleSelect = (file) => {
    selectImage(file)
    setShowCamera(false)
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6 py-4">
      <div className="text-center">
        <h2 className="font-display text-2xl font-bold">Diagnose a plant leaf</h2>
        <p className="mt-1.5 text-sm text-slate-500 dark:text-ink-muted">
          Point the camera at a leaf, snap a photo, and the vision model will spot signs of disease —
          then the RAG engine explains it using your uploaded documents.
        </p>
      </div>

      <AnimatePresence mode="wait">
        {status === 'idle' && (
          <motion.div
            key="idle"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="space-y-4"
          >
            <div className="flex justify-center gap-2">
              <Button
                variant={showCamera ? 'primary' : 'secondary'}
                icon={ScanLine}
                onClick={() => setShowCamera(true)}
              >
                Camera
              </Button>
              <Button
                variant={!showCamera ? 'primary' : 'secondary'}
                icon={Leaf}
                onClick={() => setShowCamera(false)}
              >
                Upload a photo
              </Button>
            </div>

            {showCamera ? (
              <CameraCapture onCapture={handleSelect} />
            ) : (
              <div className="panel flex flex-col items-center gap-4 rounded-panel px-6 py-12 text-center">
                <span className="flex h-14 w-14 items-center justify-center rounded-xl border border-border-light bg-slate-900/5 text-slate-500 dark:border-border dark:bg-white/[0.03] dark:text-ink-secondary">
                  <Leaf size={26} strokeWidth={1.5} />
                </span>
                <div>
                  <p className="font-display text-base font-semibold text-slate-800 dark:text-ink-primary">
                    Choose a leaf photo
                  </p>
                  <p className="mt-1 text-sm text-slate-500 dark:text-ink-muted">
                    JPG, PNG, or WEBP — a clear, well-lit close-up works best.
                  </p>
                </div>
                <label className="btn-primary inline-flex h-10 cursor-pointer items-center gap-2 px-4.5 text-sm">
                  <Leaf size={16} strokeWidth={2.25} />
                  Browse files
                  <input
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(event) => {
                      const file = event.target.files?.[0]
                      if (file) handleSelect(file)
                      event.target.value = ''
                    }}
                  />
                </label>
              </div>
            )}
          </motion.div>
        )}

        {status === 'preview' && (
          <motion.div
            key="preview"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="space-y-4"
          >
            <div className="panel overflow-hidden rounded-panel">
              <img
                src={previewUrl}
                alt="Leaf to diagnose"
                className="max-h-80 w-full object-contain"
              />
            </div>

            <div className="panel rounded-panel p-4">
              <label
                htmlFor="diagnose-query"
                className="mb-1.5 block text-xs font-medium text-slate-500 dark:text-ink-muted"
              >
                Optional: add context (e.g. &quot;Is this tomato leaf safe to eat the fruit?&quot;)
              </label>
              <textarea
                ref={queryRef}
                id="diagnose-query"
                rows={3}
                value={query}
                onChange={(event) => setQueryText(event.target.value)}
                placeholder="Optional follow-up question..."
                className="max-h-[200px] w-full resize-none rounded-lg border border-border-light bg-white/60 px-3 py-2.5 text-sm leading-relaxed text-slate-800 placeholder-slate-400 outline-none transition-colors focus:border-accent-500 focus:ring-2 focus:ring-accent-500/30 dark:border-border dark:bg-white/[0.03] dark:text-ink-primary dark:placeholder-ink-muted"
              />
            </div>

            <div className="flex flex-wrap items-center justify-center gap-3">
              <Button variant="ghost" icon={RefreshCw} onClick={reset}>
                Retake
              </Button>
              <Button variant="primary" icon={ScanLine} onClick={analyze}>
                Analyze leaf
              </Button>
            </div>
          </motion.div>
        )}

        {status === 'analyzing' && (
          <motion.div
            key="analyzing"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="space-y-4"
          >
            <div className="panel overflow-hidden rounded-panel">
              <img
                src={previewUrl}
                alt="Leaf being analyzed"
                className="max-h-80 w-full object-contain opacity-60"
              />
            </div>

            <div className="panel flex flex-col items-center gap-3 rounded-panel px-6 py-10 text-center">
              <motion.span
                animate={{ rotate: 360 }}
                transition={{ duration: 1.4, repeat: Infinity, ease: 'linear' }}
                className="flex h-14 w-14 items-center justify-center rounded-xl border border-accent-500/30 bg-accent-500/10 text-accent-500 dark:text-accent-400"
              >
                <ScanLine size={26} strokeWidth={1.75} />
              </motion.span>
              <div>
                <p className="font-display text-base font-semibold text-slate-800 dark:text-ink-primary">
                  Analyzing your leaf photo...
                </p>
                <p className="mt-1 text-sm text-slate-500 dark:text-ink-muted">
                  The vision model is examining the image — this can take a few seconds.
                </p>
              </div>
            </div>
          </motion.div>
        )}

        {(status === 'success' || status === 'error') && (
          <motion.div
            key="result"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="space-y-4"
          >
            {status === 'error' && (
              <div className="panel rounded-panel p-5 text-center">
                <p className="text-sm text-slate-600 dark:text-ink-secondary">{errorMessage}</p>
                <div className="mt-4 flex justify-center gap-3">
                  <Button variant="secondary" icon={RefreshCw} onClick={analyze}>
                    Try again
                  </Button>
                  <Button variant="ghost" onClick={reset}>
                    Choose another photo
                  </Button>
                </div>
              </div>
            )}
            {status === 'success' && <DiagnosisResult result={result} onReset={reset} />}
          </motion.div>
        )}
      </AnimatePresence>

      <p className="text-center text-[11px] text-slate-400 dark:text-ink-muted">
        Photos are analyzed by the LeafSense vision model running alongside the RAG backend.
      </p>
    </div>
  )
}
