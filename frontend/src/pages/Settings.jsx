import { useEffect, useState } from 'react'
import { BarChart3, CheckCircle2, Info, Moon, ShieldCheck, Server, Sun, ThumbsDown, ThumbsUp, Trash2, XCircle } from 'lucide-react'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import Modal from '../components/ui/Modal'
import Skeleton from '../components/ui/Skeleton'
import useTheme from '../hooks/useTheme'
import useToast from '../hooks/useToast'
import useAuth from '../hooks/useAuth'
import { getHealthStatus } from '../services/healthService'
import { getUploadHistory, removeFromUploadHistory } from '../services/documentService'
import { getFeedback, getUsageSummary, listApprovals, resolveApproval } from '../services/adminService'
import getErrorMessage from '../utils/errorMessage'

function approvalSummary(approval) {
  if (approval.action === 'web_search') return `Search the web for: "${approval.payload?.query ?? ''}"`
  if (approval.action === 'document_delete') return `Delete document ${approval.payload?.document_id ?? ''}`
  return approval.action
}

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

// Per-day rows each carry their own avg_latency_ms; the headline figure
// should be a request-weighted average across all days, not just the
// newest row's value.
const weightedAvgLatencyMs =
  usage.length === 0
    ? 0
    : Math.round(
        usage.reduce((total, row) => total + (row.request_count ?? 0) * (row.avg_latency_ms ?? 0), 0) /
          Math.max(1, usage.reduce((total, row) => total + (row.request_count ?? 0), 0))
      )

  const [approvals, setApprovals] = useState([])
  const [approvalsLoading, setApprovalsLoading] = useState(false)
  const [approvalsError, setApprovalsError] = useState(null)
  const [resolvingId, setResolvingId] = useState(null)

  useEffect(() => {
    if (user?.role !== 'admin') return undefined
    let active = true
    setApprovalsLoading(true)
    setApprovalsError(null)
    listApprovals({ status: 'pending' })
      .then((data) => {
        if (active) setApprovals(data.approvals ?? [])
      })
      .catch((error) => {
        if (active) setApprovalsError(getErrorMessage(error, 'Could not load the approval queue.'))
      })
      .finally(() => {
        if (active) setApprovalsLoading(false)
      })
    return () => {
      active = false
    }
  }, [user?.role])

  const handleResolveApproval = async (approvalId, approved) => {
    setResolvingId(approvalId)
    try {
      await resolveApproval(approvalId, approved)
      setApprovals((current) => current.filter((approval) => approval.approval_id !== approvalId))
      showToast(approved ? 'Approved.' : 'Rejected.', 'success')
    } catch (error) {
      showToast(getErrorMessage(error, 'Could not resolve the approval. Please try again.'), 'error')
    } finally {
      setResolvingId(null)
    }
  }

  const [feedback, setFeedback] = useState([])
  const [feedbackLoading, setFeedbackLoading] = useState(false)
  const [feedbackError, setFeedbackError] = useState(null)

  useEffect(() => {
    let active = true
    setFeedbackLoading(true)
    setFeedbackError(null)
    getFeedback(20)
      .then((data) => {
        if (active) setFeedback(data.events ?? [])
      })
      .catch((error) => {
        if (active) setFeedbackError(getErrorMessage(error, 'Could not load feedback.'))
      })
      .finally(() => {
        if (active) setFeedbackLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

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
          <div className="space-y-4">
            <div className="space-y-2">
              <Skeleton className="h-3 w-10" />
              {Array.from({ length: 4 }).map((_, index) => (
                <Skeleton key={index} className="h-4 w-full" />
              ))}
            </div>
            <div className="flex flex-wrap gap-2">
              {Array.from({ length: 5 }).map((_, index) => (
                <Skeleton key={index} className="h-6 w-24 rounded-full" />
              ))}
            </div>
          </div>
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
            <div className="space-y-2.5">
              {Array.from({ length: 5 }).map((_, index) => (
                <div key={index} className="flex items-center gap-2">
                  <Skeleton className="h-3 w-20 shrink-0" />
                  <Skeleton className="h-2 flex-1" />
                  <Skeleton className="h-3 w-8 shrink-0" />
                </div>
              ))}
            </div>
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
                Requests per day · avg latency {weightedAvgLatencyMs} ms
              </p>
            </div>
          )}
        </Card>
      )}

      {user?.role === 'admin' && (
        <Card padding="lg">
          <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-ink-secondary">
            <ShieldCheck size={15} strokeWidth={1.5} />
            Approval queue
          </h3>
          {approvalsLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 2 }).map((_, index) => (
                <div key={index} className="rounded-lg border border-border-light px-3.5 py-3 dark:border-border">
                  <Skeleton className="h-3 w-20" />
                  <Skeleton className="mt-2 h-4 w-3/4" />
                  <Skeleton className="mt-2 h-3 w-1/2" />
                </div>
              ))}
            </div>
          ) : approvalsError ? (
            <p className="text-sm text-danger">{approvalsError}</p>
          ) : approvals.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-ink-muted">
              No pending approvals — nothing is waiting on web_search_requires_approval or
              document_delete_requires_approval right now.
            </p>
          ) : (
            <div className="space-y-3">
              {approvals.map((approval) => {
                const isResolving = resolvingId === approval.approval_id
                const disabled = resolvingId != null && !isResolving
                return (
                  <div
                    key={approval.approval_id}
                    className="rounded-lg border border-border-light px-3.5 py-3 dark:border-border"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-ink-muted">
                          {approval.action === 'web_search' ? 'Web search' : 'Document deletion'}
                        </p>
                        <p className="mt-0.5 truncate text-sm text-slate-700 dark:text-ink-secondary">
                          {approvalSummary(approval)}
                        </p>
                        <p className="mt-0.5 text-[11px] text-slate-400 dark:text-ink-muted">
                          Requested by {approval.requested_by ?? 'unknown'} ·{' '}
                          {new Date(approval.created_at * 1000).toLocaleString()}
                        </p>
                      </div>
                      <div className="flex shrink-0 gap-1.5">
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => handleResolveApproval(approval.approval_id, false)}
                          loading={isResolving}
                          disabled={disabled}
                        >
                          Reject
                        </Button>
                        <Button
                          size="sm"
                          variant="primary"
                          onClick={() => handleResolveApproval(approval.approval_id, true)}
                          loading={isResolving}
                          disabled={disabled}
                        >
                          Approve
                        </Button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Card>
      )}

      <Card padding="lg">
        <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-ink-secondary">
          <ThumbsUp size={15} strokeWidth={1.5} />
          Recent feedback
        </h3>
        {feedbackLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, index) => (
              <div key={index} className="flex items-start gap-3">
                <Skeleton className="h-6 w-6 shrink-0 rounded-full" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-3.5 w-4/5" />
                  <Skeleton className="h-3 w-1/3" />
                </div>
              </div>
            ))}
          </div>
        ) : feedbackError ? (
          <p className="text-sm text-danger">{feedbackError}</p>
        ) : feedback.length === 0 ? (
          <p className="text-sm text-slate-500 dark:text-ink-muted">
            No feedback yet — use the thumbs control on a chat reply to record one.
          </p>
        ) : (
          <ul className="space-y-3">
            {feedback.map((event) => {
              const positive = event.rating === 'up'
              const Icon = positive ? ThumbsUp : ThumbsDown
              return (
                <li key={event.timestamp + event.message_id} className="flex items-start gap-3 text-sm">
                  <span
                    className={`mt-0.5 inline-flex shrink-0 items-center rounded-full p-1.5 ${
                      positive ? 'bg-success/10 text-success' : 'bg-danger/10 text-danger'
                    }`}
                  >
                    <Icon size={12} />
                  </span>
                  <div className="min-w-0 flex-1">
                    {event.comment ? (
                      <p className="text-slate-700 dark:text-ink-secondary">{event.comment}</p>
                    ) : (
                      <p className="text-slate-400 dark:text-ink-muted">
                        {positive ? 'Liked this reply.' : 'Disliked this reply.'}
                      </p>
                    )}
                    <p className="mt-0.5 text-xs text-slate-400 dark:text-ink-muted">
                      {new Date(event.timestamp).toLocaleString()} · {event.reviewer_id ?? 'anonymous'}
                    </p>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </Card>

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
