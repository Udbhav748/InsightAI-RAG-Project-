import { useLocation } from 'react-router-dom'
import { Menu, Search, User } from 'lucide-react'

const TITLES = {
  '/': 'Home',
  '/chat': 'Chat',
  '/history': 'History',
  '/diagnose': 'Leaf Diagnosis',
  '/upload': 'Upload Document',
  '/documents': 'Documents',
  '/settings': 'Settings',
}

export default function Navbar({ onMenuClick, onSearchClick }) {
  const { pathname } = useLocation()
  const title = TITLES[pathname] ?? 'InsightAI RAG'

  return (
    <header className="glass-panel sticky top-4 z-30 flex items-center gap-4 px-4 py-3 sm:px-6 print:hidden">
      <button
        type="button"
        onClick={onMenuClick}
        aria-label="Open menu"
        className="rounded-lg p-2 text-slate-500 hover:bg-slate-900/5 hover:text-slate-800 dark:text-ink-muted dark:hover:bg-white/[0.05] dark:hover:text-ink-primary lg:hidden"
      >
        <Menu size={18} strokeWidth={1.75} />
      </button>

      <h1 className="font-display text-base font-semibold text-slate-900 dark:text-ink-primary sm:text-lg">
        {title}
      </h1>

      <div className="ml-auto flex items-center gap-3">
        {/* Was a permanently-disabled decorative <input> — now the actual
            trigger for the command palette (Cmd/Ctrl+K), which is where
            typing/searching genuinely happens. A button styled to look
            like a search field, not a real text input, since this never
            needs its own text state. */}
        <button
          type="button"
          onClick={onSearchClick}
          className="relative hidden h-9 w-48 items-center rounded-lg border border-border-light bg-white/50 pl-9 pr-2 text-left text-sm text-slate-400 transition-colors hover:bg-white/80 dark:border-border dark:bg-white/[0.03] dark:text-ink-muted dark:hover:bg-white/[0.06] sm:flex"
        >
          <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2" />
          <span className="flex-1 truncate">Search...</span>
          <kbd className="shrink-0 rounded border border-border-light px-1.5 py-0.5 text-[10px] dark:border-border">
            ⌘K
          </kbd>
        </button>

        <button
          type="button"
          aria-label="Profile"
          className="flex h-9 w-9 items-center justify-center rounded-full border border-border-light bg-slate-100 text-slate-600 transition-colors hover:bg-slate-200 dark:border-border dark:bg-white/[0.04] dark:text-ink-secondary dark:hover:bg-white/[0.07]"
        >
          <User size={16} strokeWidth={1.75} />
        </button>
      </div>
    </header>
  )
}
