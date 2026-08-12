import { useEffect, useState } from 'react'
import { BarChart3, CheckCircle2, Info, Loader2, Moon, Server, Sun, Trash2, XCircle } from 'lucide-react'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import Modal from '../components/ui/Modal'
import useTheme from '../hooks/useTheme'
import useToast from '../hooks/useToast'
import useAuth from '../hooks/useAuth'
import { getHealthStatus } from '../services/healthService'
import { getUploadHistory, removeFromUploadHistory } from '../services/documentService'
import { getUsageSummary } from '../services/adminService'
import getErrorMessage from '../utils/errorMessage'

function StatusRow({ label, value, ok, okLabel = 'Ready', badLabel = 'Missing' }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-slate-500 dark:text-ink-muted">{label}</span>
      {ok !== undefined ? (
        <span
          className={`inline-flex items-center gap-1.5 text-xs font-medium ${
            ok ? 'text-success' : 'text-danger'
          }`}
        >
          {ok ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
          {ok ? okLabel : badLabel}
        </span>
      ) : (
        <span className="font-medium text-slate-700 dark:text-ink-secondary">{value}</span>
      )}
    </div>
  )
}

function FeatureChip({ label, enabled }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${
        enabled
          ? 'bg-success/10 text-success'
          : 'bg-slate-500/10 text-slate-500 dark:text-ink-muted'
      }`}
    >
      {label}
    </span>
  )
}

export default function Settings() {
  const { theme, setTheme } = useTheme()
  const { showToast } = useToast()
  const { user } = useAuth()
  const [confirmClear, setConfirmClear] = useState(false)
  const [health, setHealth] = useState(null)
  const [healthLoading, setHealthLoading] = useState(true)
  const [healthError, setHealthError] = useState(null)
  const [usage, setUsage] = useState([])
  const [usageLoading, setUsageLoading] = useState(false)
  const [usageError, setUsageError] = useState(null)

  useEffect(() => {
    let active = true
    getHealthStatus()
      .then((data) => {
        if (active) setHealth(data)
      })
      .catch((error) => {
        if (active) setHealthError(getErrorMessage(error, 'Backend is unreachable.'))
      })
      .finally(() => {
        if (active) setHealthLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  const clearHistory = () => {
    getUploadHistory().forEach((doc) => removeFromUploadHistory(doc.document_id))
    setConfirmClear(false)
    showToast('Document history cleared.', 'success')
  }

  const hasFallback = health?.llm?.fallback_provider

  useEffect(() => {
    if (user?.role !== 'admin') return undefined
    let active = true
    setUsageLoading(true)
    setUsageError(null)
    getUsageSummary()
      .then((data) => {
        if (active) setUsage(data.rows ?? [])
      })
      .catch((error) => {
        if (active) setUsageError(getErrorMessage(error, 'Could not load usage analytics.'))
      })
      .finally(() => {
        if (active) setUsageLoading(false)
      })
    return () => {
      active = false
    }
  }, [user?.role])

  const maxUsageCount = usage.length > 0 ? Math.max(...usage.map((row) => row.request_count)) : 1

  return (
    <div className="mx-auto max-w-2xl space-y-5 py-4">
      <div>
        <h2 className="font-display text-xl font-bold">Settings</h2>
        <p className="text-sm text-slate-500 dark:text-ink-muted">Manage your preferences.</p>
      </div>

      <Card padding="lg">
        <h3 className="mb-4 text-sm font-semibold text-slate-700 dark:text-ink-secondary">Appearance</h3>
        <div className="grid grid-cols-2 gap-3">
          {[
            { value: 'dark', label: 'Dark', icon: Moon },
            { value: 'light', label: 'Light', icon: Sun },
          ].map(({ value, label, icon: Icon }) => (
            <button
              key={value}
              type="button"
              onClick={() => setTheme(value)}
              className={`flex flex-col items-center gap-2 rounded-xl border px-4 py-5 text-sm font-medium transition-all duration-200 ${
                theme === value
                  ? 'border-accent-500/50 bg-accent-500/10 text-accent-600 dark:text-accent-500'
                  : 'border-border-light text-slate-500 hover:bg-slate-900/5 dark:border-border dark:text-ink-muted dark:hover:bg-white/[0.04]'
              }`}
            >
              <Icon size={19} strokeWidth={1.5} />
              {label}
            </button>
          ))}
        </div>
      </Card>

      <Card padding="lg">
        <h3 className="mb-1 text-sm font-semibold text-slate-700 dark:text-ink-secondary">Data</h3>
        <p className="mb-4 text-xs text-slate-500 dark:text-ink-muted">
          Document history is stored locally in this browser only.
        </p>
        <Button variant="secondary" icon={Trash2} onClick={() => setConfirmClear(true)}>
          Clear document history
        </Button>
      </Card>

      <Card padding="lg">
        <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-ink-secondary">
          <Server size={15} strokeWidth={1.5} />
          System status
        </h3>
        {healthLoading ? (
          <p className="flex items-center gap-2 text-sm text-slate-500 dark:text-ink-muted">
            <Loader2 size={14} className="animate-spin" />
            Checking backend…
          </p>
        ) : healthError ? (
          <p className="text-sm text-danger">{healthError}</p>
        ) : (
          <div className="space-y-4">
            <div>
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-ink-muted">
                LLM
              </p>
              <div className="space-y-2">
                <StatusRow label="Provider" value={health.llm.provider} />
                <StatusRow label="Provider key" ok={health.llm.provider_configured} />
                <StatusRow
                  label="Fallback"
                  value={hasFallback ? health.llm.fallback_provider : 'None'}
                  ok={hasFallback ? health.llm.fallback_configured : undefined}
                  okLabel="Ready"
                  badLabel="Missing"
                />
                <StatusRow
                  label="Model routing"
                  ok={health.llm.model_routing_enabled}
                  okLabel="On"
                  badLabel="Off"
                />
              </div>
            </div>
            <div>
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-ink-muted">
                Multi-modal RAG
              </p>
              <div className="flex flex-wrap gap-2">
                <FeatureChip
                  label="Image extraction"
                  enabled={health.multimodal.image_extraction_enabled}
                />
                <FeatureChip
                  label="Captioning"
                  enabled={health.multimodal.image_captioning_enabled}
                />
                <FeatureChip
                  label="Table extraction"
                  enabled={health.multimodal.table_extraction_enabled}
                />
                <FeatureChip label="Vision QA" enabled={health.multimodal.vision_qa_enabled} />
                <FeatureChip label="OCR" enabled={health.multimodal.ocr_available} />
              </div>
            </div>
          </div>
        )}
      </Card>

      {user?.role === 'admin' && (
        <Card padding="lg">
          <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-ink-secondary">
            <BarChart3 size={15} strokeWidth={1.5} />
            Usage analytics
          </h3>
          {usageLoading ? (
            <p className="flex items-center gap-2 text-sm text-slate-500 dark:text-ink-muted">
              <Loader2 size={14} className="animate-spin" />
              Loading usage…
            </p>
          ) : usageError ? (
            <p className="text-sm text-danger">{usageError}</p>
          ) : usage.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-ink-muted">
              No usage data yet — this is populated as requests come in.
            </p>
          ) : (
            <div className="space-y-2">
              {usage.map((row) => (
                <div key={row.day} className="flex items-center gap-2 text-xs">
                  <span className="w-20 shrink-0 text-slate-500 dark:text-ink-muted">{row.day}</span>
                  <div className="h-2 flex-1 rounded bg-slate-900/5 dark:bg-white/[0.05]">
                    <div
                      className="h-2 rounded bg-accent-500"
                      style={{ width: `${Math.min(100, (row.request_count / maxUsageCount) * 100)}%` }}
                    />
                  </div>
                  <span className="w-10 shrink-0 text-right text-slate-500 dark:text-ink-muted">
                    {row.request_count}
                  </span>
                </div>
              ))}
              <p className="pt-1 text-[11px] text-slate-400 dark:text-ink-muted">
                Requests per day · avg latency {usage[0]?.avg_latency_ms ?? 0} ms
              </p>
            </div>
          )}
        </Card>
      )}

      <Card padding="lg" className="flex items-start gap-3">
        <Info size={18} className="mt-0.5 shrink-0 text-slate-400 dark:text-ink-muted" />
        <div className="text-sm text-slate-500 dark:text-ink-muted">
          <p className="font-medium text-slate-700 dark:text-ink-secondary">InsightAI-RAG</p>
          <p>AI-powered document intelligence, built with FastAPI, FAISS, and Gemini.</p>
        </div>
      </Card>

      <Modal
        open={confirmClear}
        onClose={() => setConfirmClear(false)}
        title="Clear document history"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmClear(false)}>
              Cancel
            </Button>
            <Button variant="danger" onClick={clearHistory}>
              Clear history
            </Button>
          </>
        }
      >
        This removes all documents from your local history. It doesn't delete anything on the server.
      </Modal>
    </div>
  )
}
