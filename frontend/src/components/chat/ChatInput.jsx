import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { ArrowUp } from 'lucide-react'

const MAX_HEIGHT = 200

export default function ChatInput({ onSend, disabled }) {
  const [value, setValue] = useState('')
  const textareaRef = useRef(null)

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`
  }, [value])

  const handleSubmit = (event) => {
    event.preventDefault()
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
  }

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      handleSubmit(event)
    }
  }

  const canSend = value.trim() && !disabled

  return (
    <form
      onSubmit={handleSubmit}
      className="glass-panel flex items-end gap-2 p-2.5 shadow-soft-lg transition-shadow duration-200 focus-within:ring-2 focus-within:ring-accent-500/40"
    >
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={handleKeyDown}
        rows={1}
        placeholder="Ask a question about your documents..."
        className="max-h-[200px] flex-1 resize-none bg-transparent px-3 py-2.5 text-sm text-slate-800 placeholder-slate-400 outline-none dark:text-ink-primary dark:placeholder-ink-muted"
      />
      <motion.button
        type="submit"
        disabled={!canSend}
        whileHover={{ scale: canSend ? 1.04 : 1 }}
        whileTap={{ scale: canSend ? 0.94 : 1 }}
        transition={{ duration: 0.15, ease: 'easeOut' }}
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-accent-600/30 bg-white text-accent-600 shadow-soft-light transition-colors hover:bg-slate-50 hover:border-accent-600/50 disabled:opacity-30
          dark:border-accent-500/40 dark:bg-surface-dark-panel dark:text-accent-500 dark:shadow-none dark:hover:bg-white/[0.06] dark:hover:border-accent-500/60"
        aria-label="Send message"
      >
        <ArrowUp size={18} strokeWidth={2} />
      </motion.button>
    </form>
  )
}
