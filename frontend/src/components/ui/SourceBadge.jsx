import { FileText } from 'lucide-react'
import { getDocumentName } from '../../services/documentService'

export default function SourceBadge({ documentId, className = '' }) {
  // The backend only returns document_id (a UUID), never a filename or
  // page number. Resolve a friendly name from this browser's own upload
  // history when possible; otherwise show a generic label rather than a
  // raw UUID fragment.
  const name = getDocumentName(documentId) ?? 'Uploaded document'

  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border border-border-light bg-white/60 px-3 py-1.5 text-xs dark:border-border dark:bg-white/[0.03] ${className}`}
    >
      <FileText size={12} className="shrink-0 text-slate-400 dark:text-ink-muted" />
      <span className="max-w-[14rem] truncate font-medium text-slate-600 dark:text-ink-secondary">{name}</span>
    </span>
  )
}
