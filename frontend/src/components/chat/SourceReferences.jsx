import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { ChevronDown, FileText } from 'lucide-react'
import { getDocumentName } from '../../services/documentService'

export default function SourceReferences({ sources = [] }) {
  const [expandedIds, setExpandedIds] = useState(() => new Set())

  if (sources.length === 0) return null

  const toggle = (chunkId) => {
    setExpandedIds((current) => {
      const next = new Set(current)
      if (next.has(chunkId)) {
        next.delete(chunkId)
      } else {
        next.add(chunkId)
      }
      return next
    })
  }

  return (
    <div className="mt-3 space-y-1.5 border-t border-border-light pt-3 dark:border-border">
      {sources.map((source) => {
        const isExpanded = expandedIds.has(source.chunk_id)
        // The backend only returns document_id (a UUID), never a filename.
        // Resolve a friendly name from this browser's own upload history
        // when possible; otherwise show a generic label rather than a raw
        // UUID fragment.
        const documentName = getDocumentName(source.document_id) ?? 'Uploaded document'

        return (
          <div
            key={source.chunk_id}
            className="overflow-hidden rounded-lg border border-border-light bg-white/50 dark:border-border dark:bg-white/[0.03]"
          >
            <button
              type="button"
              onClick={() => toggle(source.chunk_id)}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs transition-colors hover:bg-slate-900/[0.02] dark:hover:bg-white/[0.02]"
            >
              <FileText size={12} className="shrink-0 text-slate-400 dark:text-ink-muted" />
              <span className="flex-1 truncate font-medium text-slate-600 dark:text-ink-secondary">
                {documentName}
              </span>
              <motion.span
                animate={{ rotate: isExpanded ? 180 : 0 }}
                transition={{ duration: 0.2 }}
                className="shrink-0 text-slate-400 dark:text-ink-muted"
              >
                <ChevronDown size={12} />
              </motion.span>
            </button>

            <AnimatePresence initial={false}>
              {isExpanded && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
                  className="overflow-hidden"
                >
                  <p className="px-3 pb-2.5 text-xs text-slate-600 dark:text-ink-secondary">
                    {source.excerpt}
                  </p>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )
      })}
    </div>
  )
}
