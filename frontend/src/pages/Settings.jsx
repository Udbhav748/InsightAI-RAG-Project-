import { useState } from 'react'
import { Info, Moon, Sun, Trash2 } from 'lucide-react'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import Modal from '../components/ui/Modal'
import useTheme from '../hooks/useTheme'
import useToast from '../hooks/useToast'
import { getUploadHistory, removeFromUploadHistory } from '../services/documentService'

export default function Settings() {
  const { theme, setTheme } = useTheme()
  const { showToast } = useToast()
  const [confirmClear, setConfirmClear] = useState(false)

  const clearHistory = () => {
    getUploadHistory().forEach((doc) => removeFromUploadHistory(doc.document_id))
    setConfirmClear(false)
    showToast('Document history cleared.', 'success')
  }

  return (
    <div className="mx-auto max-w-2xl space-y-5 py-4">
      <div>
        <h2 className="font-display text-xl font-bold">Settings</h2>
        <p className="text-sm text-slate-500 dark:text-ink-muted">Manage your preferences.</p>
      </div>

      <Card padding="lg">
        <h3 className="mb-4 text-sm font-semibold text-slate-700 dark:text-ink-secondary">Appearance</h3>
        <div className="grid grid-cols-2 gap-3">
          {[
            { value: 'dark', label: 'Dark', icon: Moon },
            { value: 'light', label: 'Light', icon: Sun },
          ].map(({ value, label, icon: Icon }) => (
            <button
              key={value}
              type="button"
              onClick={() => setTheme(value)}
              className={`flex flex-col items-center gap-2 rounded-xl border px-4 py-5 text-sm font-medium transition-all duration-200 ${
                theme === value
                  ? 'border-accent-500/50 bg-accent-500/10 text-accent-600 dark:text-accent-500'
                  : 'border-border-light text-slate-500 hover:bg-slate-900/5 dark:border-border dark:text-ink-muted dark:hover:bg-white/[0.04]'
              }`}
            >
              <Icon size={19} strokeWidth={1.5} />
              {label}
            </button>
          ))}
        </div>
      </Card>

      <Card padding="lg">
        <h3 className="mb-1 text-sm font-semibold text-slate-700 dark:text-ink-secondary">Data</h3>
        <p className="mb-4 text-xs text-slate-500 dark:text-ink-muted">
          Document history is stored locally in this browser only.
        </p>
        <Button variant="secondary" icon={Trash2} onClick={() => setConfirmClear(true)}>
          Clear document history
        </Button>
      </Card>

      <Card padding="lg" className="flex items-start gap-3">
        <Info size={18} className="mt-0.5 shrink-0 text-slate-400 dark:text-ink-muted" />
        <div className="text-sm text-slate-500 dark:text-ink-muted">
          <p className="font-medium text-slate-700 dark:text-ink-secondary">InsightAI-RAG</p>
          <p>AI-powered document intelligence, built with FastAPI, FAISS, and Gemini.</p>
        </div>
      </Card>

      <Modal
        open={confirmClear}
        onClose={() => setConfirmClear(false)}
        title="Clear document history"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmClear(false)}>
              Cancel
            </Button>
            <Button variant="danger" onClick={clearHistory}>
              Clear history
            </Button>
          </>
        }
      >
        This removes all documents from your local history. It doesn't delete anything on the server.
      </Modal>
    </div>
  )
}
