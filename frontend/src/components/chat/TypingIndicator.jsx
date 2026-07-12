import { motion } from 'framer-motion'
import { Sparkles } from 'lucide-react'

export default function TypingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      className="flex items-start gap-3"
    >
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border-light bg-slate-100 text-slate-500 dark:border-border dark:bg-white/[0.04] dark:text-ink-secondary">
        <Sparkles size={15} strokeWidth={1.75} />
      </span>
      <div className="panel flex items-center gap-1.5 rounded-2xl rounded-tl-md px-4 py-3.5">
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="h-1.5 w-1.5 rounded-full bg-slate-400 dark:bg-ink-muted"
            animate={{ opacity: [0.3, 1, 0.3], y: [0, -3, 0] }}
            transition={{ duration: 1.1, repeat: Infinity, delay: i * 0.15, ease: 'easeInOut' }}
          />
        ))}
      </div>
    </motion.div>
  )
}
