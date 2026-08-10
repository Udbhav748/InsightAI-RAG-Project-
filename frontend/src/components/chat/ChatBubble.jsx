import { useState } from 'react'
import { motion } from 'framer-motion'
import { Check, ClipboardList, Copy, RotateCcw, Sparkles, ThumbsDown, ThumbsUp, User } from 'lucide-react'
import AgentTraceStrip from './AgentTraceStrip'
import CitedAnswer from './CitedAnswer'
import RubricReviewModal from './RubricReviewModal'
import { sendFeedback } from '../../services/feedbackService'
import useToast from '../../hooks/useToast'
import getErrorMessage from '../../utils/errorMessage'

export default function ChatBubble({ message, isLast, onRegenerate }) {
  const [copied, setCopied] = useState(false)
  const [feedback, setFeedback] = useState(null) // null | 'up' | 'down'
  const [rubricModalOpen, setRubricModalOpen] = useState(false)
  const [rubricSubmitted, setRubricSubmitted] = useState(false)
  const { showToast } = useToast()
  const isUser = message.role === 'user'

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // Clipboard API unavailable — silently ignore, copy is a nicety.
    }
  }

  const handleFeedback = async (rating) => {
    if (feedback) return // already rated — send once per message
    setFeedback(rating) // optimistic + disables both buttons immediately
    try {
      await sendFeedback(message.id, rating)
    } catch (error) {
      setFeedback(null) // let the user retry
      showToast(getErrorMessage(error, 'Could not record feedback.'), 'error')
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
      className={`flex items-start gap-3 ${isUser ? 'flex-row-reverse' : ''}`}
    >
      <span
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border ${
          isUser
            ? 'border-border-light bg-slate-200 text-slate-600 dark:border-border dark:bg-white/[0.06] dark:text-ink-secondary'
            : 'border-border-light bg-slate-100 text-slate-500 dark:border-border dark:bg-white/[0.04] dark:text-ink-secondary'
        }`}
      >
        {isUser ? <User size={15} strokeWidth={1.75} /> : <Sparkles size={15} strokeWidth={1.75} />}
      </span>

      <div className={`flex max-w-[85%] flex-col sm:max-w-[75%] ${isUser ? 'items-end' : 'items-start'}`}>
        <div
          className={
            isUser
              ? 'rounded-2xl rounded-tr-md bg-slate-900/[0.04] px-4 py-3 text-sm text-slate-800 dark:bg-white/[0.06] dark:text-ink-primary'
              : 'panel rounded-2xl rounded-tl-md px-4 py-3.5 text-sm text-slate-700 dark:text-ink-secondary'
          }
        >
          {!isUser && <AgentTraceStrip trace={message.trace} isStreaming={message.isStreaming} />}
          {!isUser && !message.isStreaming ? (
            <CitedAnswer text={message.content} sources={message.sources} />
          ) : (
            <p className="whitespace-pre-wrap leading-relaxed">
              {message.content}
              {message.isStreaming && (
                <span className="ml-0.5 inline-block h-3.5 w-[2px] animate-pulse bg-slate-400 align-middle dark:bg-ink-muted" />
              )}
            </p>
          )}
        </div>

        {!isUser && !message.isStreaming && (
          <div className="mt-1.5 flex items-center gap-1 px-1">
            <button
              type="button"
              onClick={handleCopy}
              className="flex items-center gap-1 rounded-lg px-1.5 py-1 text-xs text-slate-400 transition-colors hover:bg-slate-900/5 hover:text-slate-600 dark:text-ink-muted dark:hover:bg-white/[0.05] dark:hover:text-ink-secondary"
            >
              {copied ? <Check size={12} /> : <Copy size={12} />}
              {copied ? 'Copied' : 'Copy'}
            </button>
            {isLast && (
              <button
                type="button"
                onClick={onRegenerate}
                className="flex items-center gap-1 rounded-lg px-1.5 py-1 text-xs text-slate-400 transition-colors hover:bg-slate-900/5 hover:text-slate-600 dark:text-ink-muted dark:hover:bg-white/[0.05] dark:hover:text-ink-secondary"
              >
                <RotateCcw size={12} strokeWidth={1.75} />
                Regenerate
              </button>
            )}
            {!message.isError && (
              <>
                <button
                  type="button"
                  onClick={() => handleFeedback('up')}
                  disabled={feedback != null}
                  aria-pressed={feedback === 'up'}
                  aria-label="Good response"
                  className={`flex items-center rounded-lg p-1.5 transition-colors disabled:pointer-events-none ${
                    feedback === 'up'
                      ? 'text-success'
                      : 'text-slate-400 hover:bg-slate-900/5 hover:text-slate-600 disabled:opacity-30 dark:text-ink-muted dark:hover:bg-white/[0.05] dark:hover:text-ink-secondary'
                  }`}
                >
                  <ThumbsUp size={12} strokeWidth={1.75} />
                </button>
                <button
                  type="button"
                  onClick={() => handleFeedback('down')}
                  disabled={feedback != null}
                  aria-pressed={feedback === 'down'}
                  aria-label="Bad response"
                  className={`flex items-center rounded-lg p-1.5 transition-colors disabled:pointer-events-none ${
                    feedback === 'down'
                      ? 'text-danger'
                      : 'text-slate-400 hover:bg-slate-900/5 hover:text-slate-600 disabled:opacity-30 dark:text-ink-muted dark:hover:bg-white/[0.05] dark:hover:text-ink-secondary'
                  }`}
                >
                  <ThumbsDown size={12} strokeWidth={1.75} />
                </button>
                {feedback && !rubricSubmitted && (
                  <button
                    type="button"
                    onClick={() => setRubricModalOpen(true)}
                    className="flex items-center gap-1 rounded-lg px-1.5 py-1 text-xs text-slate-400 transition-colors hover:bg-slate-900/5 hover:text-slate-600 dark:text-ink-muted dark:hover:bg-white/[0.05] dark:hover:text-ink-secondary"
                  >
                    <ClipboardList size={12} strokeWidth={1.75} />
                    Detailed review
                  </button>
                )}
                {rubricSubmitted && (
                  <span className="flex items-center gap-1 px-1.5 py-1 text-xs text-success">
                    <Check size={12} strokeWidth={1.75} />
                    Reviewed
                  </span>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {feedback && (
        <RubricReviewModal
          open={rubricModalOpen}
          onClose={() => setRubricModalOpen(false)}
          messageId={message.id}
          rating={feedback}
          onSubmitted={() => setRubricSubmitted(true)}
        />
      )}
    </motion.div>
  )
}
