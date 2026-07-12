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

  return (
    <form
      onSubmit={handleSubmit}
      className="glass-panel flex items-end gap-2 rounded-3xl p-2.5 shadow-soft-lg transition-shadow duration-200 focus-within:ring-2 focus-within:ring-accent-400/50"
    >
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={handleKeyDown}
        rows={1}
        placeholder="Ask a question about your documents..."
        className="max-h-[200px] flex-1 resize-none bg-transparent px-3 py-2.5 text-sm text-slate-800 placeholder-slate-400 outline-none dark:text-slate-100"
      />
      <motion.button
        type="submit"
        disabled={!value.trim() || disabled}
        whileHover={{ scale: value.trim() && !disabled ? 1.05 : 1 }}
        whileTap={{ scale: value.trim() && !disabled ? 0.92 : 1 }}
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-accent-500 to-accent-glow text-white shadow-glow-sm transition-opacity disabled:opacity-30"
        aria-label="Send message"
      >
        <ArrowUp size={18} strokeWidth={2.5} />
      </motion.button>
    </form>
  )
}
