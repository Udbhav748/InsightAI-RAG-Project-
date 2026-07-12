import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { ChevronDown } from 'lucide-react'
import SourceBadge from '../ui/SourceBadge'
import { getDocumentName } from '../../services/documentService'

export default function SourceReferences({ sources = [], retrievedChunks = [] }) {
  const [expanded, setExpanded] = useState(false)

  if (sources.length === 0) return null

  return (
    <div className="mt-3 border-t border-border-light pt-3 dark:border-border">
      <div className="flex flex-wrap items-center gap-2">
        {sources.map((documentId) => (
          <SourceBadge key={documentId} documentId={documentId} />
        ))}

        {retrievedChunks.length > 0 && (
          <button
            type="button"
            onClick={() => setExpanded((current) => !current)}
            className="flex items-center gap-1 rounded-full px-2 py-1 text-xs font-medium text-slate-400 transition-colors hover:text-accent-600 dark:text-ink-muted dark:hover:text-accent-500"
          >
            {expanded ? 'Hide excerpts' : 'Show excerpts'}
            <motion.span animate={{ rotate: expanded ? 180 : 0 }} transition={{ duration: 0.2 }}>
              <ChevronDown size={12} />
            </motion.span>
          </button>
        )}
      </div>

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
              {retrievedChunks.map((chunk) => (
                <div
                  key={chunk.chunk_id}
                  className="rounded-lg border border-border-light bg-white/50 p-3 text-xs dark:border-border dark:bg-white/[0.03]"
                >
                  <p className="mb-1 font-medium text-slate-500 dark:text-ink-muted">
                    {getDocumentName(chunk.document_id) ?? 'Uploaded document'}
                  </p>
                  <p className="line-clamp-2 text-slate-600 dark:text-ink-secondary">{chunk.text}</p>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
