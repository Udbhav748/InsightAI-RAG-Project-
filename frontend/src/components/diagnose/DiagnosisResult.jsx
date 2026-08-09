import { motion } from 'framer-motion'
import { AlertTriangle, Leaf, Sparkles } from 'lucide-react'
import SourceReferences from '../chat/SourceReferences'
import Button from '../ui/Button'

function confidenceColor(confidence) {
  if (confidence >= 0.8) return 'text-success'
  if (confidence >= 0.6) return 'text-warning'
  return 'text-danger'
}

export default function DiagnosisResult({ result, onReset }) {
  const { diagnosis, answer, sources, processing_time } = result
  const confidence = diagnosis?.confidence

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className="space-y-4"
    >
      {diagnosis && (
        <div className="panel rounded-panel p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-medium uppercase tracking-wider text-slate-400 dark:text-ink-muted">
                Detected on the leaf
              </p>
              <h3 className="mt-1 font-display text-xl font-bold capitalize text-slate-900 dark:text-ink-primary">
                {diagnosis.disease || 'Unknown condition'}
              </h3>
              <p className="mt-0.5 text-sm capitalize text-slate-500 dark:text-ink-muted">
                {diagnosis.crop} leaf
              </p>
            </div>
            <div className="text-right">
              <p className="text-xs font-medium uppercase tracking-wider text-slate-400 dark:text-ink-muted">
                Confidence
              </p>
              <p className={`mt-1 font-display text-2xl font-bold ${confidenceColor(confidence ?? 0)}`}>
                {confidence != null ? `${Math.round(confidence * 100)}%` : '—'}
              </p>
            </div>
          </div>

          <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-900/5 dark:bg-white/[0.06]">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${Math.round((confidence ?? 0) * 100)}%` }}
              transition={{ duration: 0.6, ease: 'easeOut', delay: 0.15 }}
              className="h-full rounded-full bg-accent-500"
            />
          </div>

          {diagnosis.low_confidence && (
            <div className="mt-4 flex items-start gap-2.5 rounded-lg border border-warning/30 bg-warning/10 px-3.5 py-2.5 text-sm text-amber-800 dark:text-amber-200">
              <AlertTriangle size={16} strokeWidth={1.75} className="mt-0.5 shrink-0" />
              <p>
                Confidence is low. The photo may not clearly show the disease — consider a sharper,
                closer shot or better lighting.
              </p>
            </div>
          )}

          <p className="mt-3 text-[11px] text-slate-400 dark:text-ink-muted">
            Raw model class: <code className="font-mono">{diagnosis.raw_class}</code>
          </p>
        </div>
      )}

      <div className="panel rounded-panel p-5">
        <div className="mb-3 flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-accent-500/15 text-accent-600 dark:text-accent-500">
            <Sparkles size={13} strokeWidth={2} />
          </span>
          <h3 className="font-display text-sm font-semibold text-slate-800 dark:text-ink-primary">
            Diagnosis explained
          </h3>
        </div>
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700 dark:text-ink-secondary">
          {answer}
        </p>
        <SourceReferences sources={sources} />
      </div>

      <div className="flex flex-wrap items-center justify-center gap-3">
        <Button variant="primary" icon={Leaf} onClick={onReset}>
          Diagnose another leaf
        </Button>
      </div>

      <p className="text-center text-[11px] text-slate-400 dark:text-ink-muted">
        {processing_time != null ? `Processed in ${processing_time.toFixed(2)}s · ` : ''}
        Not a veterinary or medical diagnosis. Always confirm with an expert.
      </p>
    </motion.div>
  )
}
