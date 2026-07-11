import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { ChevronDown, FileText } from 'lucide-react'

export default function SourceReferences({ sources = [], retrievedChunks = [] }) {
  const [expanded, setExpanded] = useState(false)

  if (sources.length === 0) return null

  return (
    <div className="mt-3 border-t border-border-light pt-3 dark:border-border">
      <button
        type="button"
        onClick={() => setExpanded((current) => !current)}
        className="flex items-center gap-1.5 text-xs font-medium text-slate-500 transition-colors hover:text-accent-600 dark:text-slate-400 dark:hover:text-accent-400"
      >
        <FileText size={12} />
        {sources.length} source{sources.length === 1 ? '' : 's'}
        <motion.span animate={{ rotate: expanded ? 180 : 0 }} transition={{ duration: 0.2 }}>
          <ChevronDown size={12} />
        </motion.span>
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden"
          >
            <div className="mt-2 space-y-2">
              {retrievedChunks.length > 0
                ? retrievedChunks.map((chunk) => (
                    <div
                      key={chunk.chunk_id}
                      className="rounded-xl border border-border-light bg-white/50 p-3 text-xs dark:border-border dark:bg-white/5"
                    >
                      <div className="mb-1 flex items-center justify-between text-slate-400">
                        <span className="font-mono">{chunk.document_id.slice(0, 8)}</span>
                        <span>{Math.round(chunk.score * 100)}% match</span>
                      </div>
                      <p className="line-clamp-2 text-slate-600 dark:text-slate-300">{chunk.text}</p>
                    </div>
                  ))
                : sources.map((source) => (
                    <div
                      key={source}
                      className="rounded-xl border border-border-light bg-white/50 px-3 py-2 text-xs font-mono text-slate-500 dark:border-border dark:bg-white/5 dark:text-slate-400"
                    >
                      {source}
                    </div>
                  ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
