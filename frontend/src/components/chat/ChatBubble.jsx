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
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className={`flex items-start gap-3 ${isUser ? 'flex-row-reverse' : ''}`}
    >
      <span
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl ${
          isUser
            ? 'bg-slate-200 text-slate-600 dark:bg-white/10 dark:text-slate-300'
            : 'bg-gradient-to-br from-accent-500 to-accent-glow text-white shadow-glow-sm'
        }`}
      >
        {isUser ? <User size={15} /> : <Sparkles size={15} />}
      </span>

      <div className={`flex max-w-[85%] flex-col sm:max-w-[75%] ${isUser ? 'items-end' : 'items-start'}`}>
        <div
          className={
            isUser
              ? 'rounded-2xl rounded-tr-md bg-gradient-to-br from-accent-500 to-accent-600 px-4 py-3 text-sm text-white shadow-glow-sm'
              : 'glass-panel rounded-2xl rounded-tl-md px-4 py-3.5 text-sm text-slate-700 dark:text-slate-200'
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
              className="flex items-center gap-1 rounded-lg px-1.5 py-1 text-xs text-slate-400 transition-colors hover:bg-slate-900/5 hover:text-slate-600 dark:hover:bg-white/5 dark:hover:text-slate-300"
            >
              {copied ? <Check size={12} /> : <Copy size={12} />}
              {copied ? 'Copied' : 'Copy'}
            </button>
            {isLast && (
              <button
                type="button"
                onClick={onRegenerate}
                className="flex items-center gap-1 rounded-lg px-1.5 py-1 text-xs text-slate-400 transition-colors hover:bg-slate-900/5 hover:text-slate-600 dark:hover:bg-white/5 dark:hover:text-slate-300"
              >
                <RotateCcw size={12} />
                Regenerate
              </button>
            )}
          </div>
        )}
      </div>
    </motion.div>
  )
}
