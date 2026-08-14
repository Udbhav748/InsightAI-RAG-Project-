import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  CheckCircle2,
  Leaf,
  MessageCircle,
  Printer,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import Button from '../ui/Button'
import { getSeverityInfo } from '../../utils/agronomyData'

function confidenceColor(confidence) {
  if (confidence >= 0.85) return 'text-emerald-600 dark:text-emerald-400'
  if (confidence >= 0.65) return 'text-amber-600 dark:text-amber-400'
  return 'text-rose-600 dark:text-rose-400'
}

function confidenceBarColor(confidence) {
  if (confidence >= 0.85) return 'bg-emerald-500'
  if (confidence >= 0.65) return 'bg-amber-500'
  return 'bg-rose-500'
}

/**
 * Prediction Hero Card displaying detected crop, disease diagnosis,
 * severity level badge, animated confidence score bar, and fast actions.
 */
export default function PredictionHeroCard({
  diagnosis,
  sessionId,
  processingTime,
  onReset,
}) {
  const navigate = useNavigate()
  const confidence = diagnosis?.confidence ?? 0
  const confidencePercent = Math.round(confidence * 100)
  const isHealthy = (diagnosis?.disease || '').toLowerCase().includes('healthy')
  const severity = getSeverityInfo(diagnosis?.disease, confidence)

  const handleContinueChat = () => {
    navigate('/chat', { state: { sessionId } })
  }

  const handlePrint = () => {
    window.print()
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
      className="panel relative overflow-hidden rounded-panel border border-border-light p-6 shadow-soft dark:border-border"
    >
      {/* Background ambient gradient glow */}
      <div
        className={`pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full blur-3xl opacity-20 ${
          isHealthy ? 'bg-emerald-500' : severity.level === 'Severe' ? 'bg-rose-500' : 'bg-amber-500'
        }`}
      />

      <div className="relative space-y-5">
        {/* Top Tag & Severity Badge */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent-500/15 text-accent-600 dark:text-accent-400">
              <Leaf size={15} strokeWidth={2} />
            </span>
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-ink-muted">
              LeafSense Vision Diagnosis
            </span>
          </div>

          {/* Severity Level Badge */}
          <div
            data-testid="severity-badge"
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${severity.badge}`}
          >
            {isHealthy ? (
              <ShieldCheck size={14} className="shrink-0" />
            ) : severity.level === 'Severe' ? (
              <ShieldAlert size={14} className="shrink-0" />
            ) : (
              <AlertTriangle size={14} className="shrink-0" />
            )}
            <span>Severity: {severity.level}</span>
          </div>
        </div>

        {/* Hero Plant & Disease Titles */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-12 sm:items-end">
          <div className="space-y-1 sm:col-span-8">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-ink-muted">
              Crop Species: <span className="font-semibold capitalize text-slate-800 dark:text-ink-primary">{diagnosis?.crop || 'Plant'}</span>
            </p>
            <h2 className="font-display text-2xl font-bold capitalize tracking-tight text-slate-900 sm:text-3xl dark:text-ink-primary">
              {diagnosis?.disease || 'Condition Undetermined'}
            </h2>
            <p className="text-xs text-slate-600 dark:text-ink-secondary">
              {severity.description}
            </p>
          </div>

          {/* Confidence Score Display */}
          <div className="rounded-xl border border-border-light bg-slate-900/[0.03] p-3 text-right sm:col-span-4 dark:border-border dark:bg-white/[0.02]">
            <span className="text-[11px] font-medium uppercase tracking-wider text-slate-500 dark:text-ink-muted">
              Classification Confidence
            </span>
            <div data-testid="confidence-score-value" className={`font-display text-3xl font-extrabold ${confidenceColor(confidence)}`}>
              {confidencePercent}%
            </div>
            <span className="text-[10px] text-slate-400 dark:text-ink-muted">
              Deep CNN & ViT Ensemble
            </span>
          </div>
        </div>

        {/* Animated Confidence Bar */}
        <div className="space-y-1.5">
          <div className="flex justify-between text-xs text-slate-500 dark:text-ink-muted">
            <span>Model certainty score</span>
            <span className="font-medium">{confidencePercent}%</span>
          </div>
          <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-900/5 dark:bg-white/[0.06]">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${confidencePercent}%` }}
              transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1], delay: 0.1 }}
              className={`h-full rounded-full ${confidenceBarColor(confidence)}`}
            />
          </div>
        </div>

        {/* Low Confidence Advisory */}
        {diagnosis?.low_confidence && (
          <div className="flex items-start gap-2.5 rounded-xl border border-warning/30 bg-warning/10 p-3 text-xs text-amber-900 dark:text-amber-200">
            <AlertTriangle size={16} className="mt-0.5 shrink-0 text-warning" />
            <p>
              <strong>Low confidence prediction:</strong> The leaf image may have had suboptimal lighting or partial occlusion. For critical field decisions, consider uploading a closer, well-lit shot.
            </p>
          </div>
        )}

        {/* Raw model class & metadata info */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border-light pt-3 text-[11px] text-slate-500 dark:border-border dark:text-ink-muted">
          <div>
            Raw Model Class: <code className="font-mono font-semibold text-slate-700 dark:text-ink-secondary">{diagnosis?.raw_class || 'N/A'}</code>
          </div>
          {processingTime != null && (
            <div>
              Processed in {typeof processingTime === 'number' ? processingTime.toFixed(2) : processingTime}s
            </div>
          )}
        </div>

        {/* Fast Action Buttons */}
        <div className="flex flex-wrap items-center gap-3 pt-1">
          <Button
            type="button"
            variant="primary"
            icon={MessageCircle}
            onClick={handleContinueChat}
            disabled={!sessionId}
          >
            Consult in AI Chat
          </Button>

          <Button
            type="button"
            variant="secondary"
            icon={RefreshCw}
            onClick={onReset}
          >
            Diagnose Another Leaf
          </Button>

          <Button
            type="button"
            variant="ghost"
            icon={Printer}
            onClick={handlePrint}
            className="hidden sm:inline-flex"
          >
            Print Prescription
          </Button>
        </div>
      </div>
    </motion.div>
  )
}
