import { useState } from 'react'
import { motion } from 'framer-motion'
import { Check, Copy, RotateCcw, Sparkles, User } from 'lucide-react'
import SourceReferences from './SourceReferences'

export default function ChatBubble({ message, isLast, onRegenerate }) {
  const [copied, setCopied] = useState(false)
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
          <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
          {!isUser && (
            <SourceReferences sources={message.sources} retrievedChunks={message.retrievedChunks} />
          )}
        </div>

        {!isUser && (
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
          </div>
        )}
      </div>
    </motion.div>
  )
}
