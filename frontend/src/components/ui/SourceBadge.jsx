import { FileText } from 'lucide-react'
import { getDocumentName } from '../../services/documentService'

function scoreTone(score) {
  if (score >= 0.7) return 'text-success'
  if (score >= 0.4) return 'text-warning'
  return 'text-slate-400 dark:text-slate-500'
}

export default function SourceBadge({ documentId, score, className = '' }) {
  const name = getDocumentName(documentId)

  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border border-border-light bg-white/60 px-3 py-1.5 text-xs dark:border-border dark:bg-white/5 ${className}`}
    >
      <FileText size={12} className="shrink-0 text-accent-500 dark:text-accent-400" />
      <span className="max-w-[12rem] truncate font-medium text-slate-600 dark:text-slate-300">
        {name ?? `Document ${documentId.slice(0, 8)}`}
      </span>
      {typeof score === 'number' && (
        <span className={`font-mono font-semibold ${scoreTone(score)}`}>{Math.round(score * 100)}%</span>
      )}
    </span>
  )
}
