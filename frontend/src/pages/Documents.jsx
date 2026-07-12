import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowUpDown, FileText, Trash2, UploadCloud } from 'lucide-react'
import SearchInput from '../components/ui/SearchInput'
import StatusBadge from '../components/ui/StatusBadge'
import EmptyState from '../components/ui/EmptyState'
import Button from '../components/ui/Button'
import Modal from '../components/ui/Modal'
import { deleteDocument, getUploadHistory, removeFromUploadHistory } from '../services/documentService'
import useToast from '../hooks/useToast'
import getErrorMessage from '../utils/errorMessage'

function formatDate(iso) {
  if (!iso) return 'Unknown date'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return 'Unknown date'
  return date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

function effectiveStatus(doc) {
  if (doc.status === 'processed' && doc.total_chunks === 0) return 'warning'
  return doc.status ?? 'uploaded'
}

const SORT_OPTIONS = [
  { value: 'newest', label: 'Newest first' },
  { value: 'oldest', label: 'Oldest first' },
  { value: 'name', label: 'Name (A-Z)' },
]

export default function Documents() {
  const [documents, setDocuments] = useState([])
  const [query, setQuery] = useState('')
  const [sortBy, setSortBy] = useState('newest')
  const [pendingDelete, setPendingDelete] = useState(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const navigate = useNavigate()
  const { showToast } = useToast()

  useEffect(() => {
    setDocuments(getUploadHistory())
  }, [])

  const filtered = useMemo(() => {
    const list = documents.filter((doc) =>
      doc.original_filename.toLowerCase().includes(query.toLowerCase())
    )
    const sorted = [...list].sort((a, b) => {
      if (sortBy === 'name') return a.original_filename.localeCompare(b.original_filename)
      const dateA = new Date(a.uploaded_at).getTime() || 0
      const dateB = new Date(b.uploaded_at).getTime() || 0
      return sortBy === 'oldest' ? dateA - dateB : dateB - dateA
    })
    return sorted
  }, [documents, query, sortBy])

  const confirmDelete = async () => {
    if (!pendingDelete) return
    setIsDeleting(true)
    try {
      await deleteDocument(pendingDelete.document_id)
      setDocuments(removeFromUploadHistory(pendingDelete.document_id))
      showToast(`${pendingDelete.original_filename} deleted.`, 'success')
      setPendingDelete(null)
    } catch (error) {
      showToast(getErrorMessage(error, 'Failed to delete document. Please try again.'), 'error')
    } finally {
      setIsDeleting(false)
    }
  }

  return (
    <div className="space-y-5 py-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="font-display text-xl font-bold">Documents</h2>
          <p className="text-sm text-slate-500 dark:text-ink-muted">
            {documents.length} document{documents.length === 1 ? '' : 's'} in this browser's history
          </p>
        </div>
        <Button variant="primary" icon={UploadCloud} onClick={() => navigate('/upload')}>
          Upload
        </Button>
      </div>

      {documents.length > 0 && (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <SearchInput value={query} onChange={setQuery} placeholder="Search documents..." className="sm:w-72" />
          <div className="relative sm:ml-auto">
            <ArrowUpDown size={13} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 dark:text-ink-muted" />
            <select
              value={sortBy}
              onChange={(event) => setSortBy(event.target.value)}
              className="input w-full appearance-none py-2 pl-8 pr-8 sm:w-44"
            >
              {SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

      {documents.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No documents yet"
          description="Upload your first PDF to start building your knowledge base."
          action={
            <Button variant="primary" icon={UploadCloud} onClick={() => navigate('/upload')}>
              Upload a document
            </Button>
          }
        />
      ) : filtered.length === 0 ? (
        <EmptyState icon={FileText} title="No matches" description="Try a different search term." />
      ) : (
        <div className="panel divide-y divide-border-light overflow-hidden dark:divide-border">
          {filtered.map((doc, index) => (
            <motion.div
              key={doc.document_id}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.25, delay: index * 0.03 }}
              className="flex flex-col gap-3 px-5 py-4 transition-colors hover:bg-slate-900/[0.02] dark:hover:bg-white/[0.02] sm:flex-row sm:items-center"
            >
              <div className="flex min-w-0 flex-1 items-center gap-3">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border-light bg-slate-900/5 text-slate-500 dark:border-border dark:bg-white/[0.03] dark:text-ink-secondary">
                  <FileText size={18} strokeWidth={1.5} />
                </span>
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-slate-800 dark:text-ink-primary">
                    {doc.original_filename}
                  </p>
                  <p className="text-xs text-slate-400 dark:text-ink-muted">{formatDate(doc.uploaded_at)}</p>
                </div>
              </div>

              <div className="flex items-center gap-4 pl-[3.25rem] sm:pl-0">
                <span className="w-28 shrink-0 text-xs text-slate-500 dark:text-ink-muted">
                  {doc.total_pages != null ? `${doc.total_pages} pg · ${doc.total_chunks} chunks` : '—'}
                </span>
                <StatusBadge status={effectiveStatus(doc)} />
                <button
                  type="button"
                  onClick={() => setPendingDelete(doc)}
                  aria-label={`Delete ${doc.original_filename}`}
                  className="ml-auto rounded-lg p-2 text-slate-400 transition-colors hover:bg-danger/10 hover:text-danger dark:text-ink-muted sm:ml-0"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            </motion.div>
          ))}
        </div>
      )}

      <Modal
        open={!!pendingDelete}
        onClose={() => setPendingDelete(null)}
        title="Remove document"
        footer={
          <>
            <Button variant="secondary" onClick={() => setPendingDelete(null)} disabled={isDeleting}>
              Cancel
            </Button>
            <Button variant="danger" onClick={confirmDelete} loading={isDeleting}>
              Delete
            </Button>
          </>
        }
      >
        Delete <span className="font-medium text-slate-800 dark:text-ink-primary">{pendingDelete?.original_filename}</span>?
        This permanently removes it from the server — its content will no longer be searchable in chat. This can't be undone.
      </Modal>
    </div>
  )
}
