import { useLocation } from 'react-router-dom'
import { Menu, Search, User } from 'lucide-react'

const TITLES = {
  '/': 'Home',
  '/chat': 'Chat',
  '/upload': 'Upload Document',
  '/documents': 'Documents',
  '/settings': 'Settings',
}

export default function Navbar({ onMenuClick }) {
  const { pathname } = useLocation()
  const title = TITLES[pathname] ?? 'InsightAI RAG'

  return (
    <header className="glass-panel sticky top-4 z-30 flex items-center gap-4 px-4 py-3 sm:px-6">
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
        <div className="relative hidden sm:block">
          <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 dark:text-ink-muted" />
          <input
            type="text"
            placeholder="Search..."
            disabled
            className="h-9 w-48 rounded-lg border border-border-light bg-white/50 pl-9 pr-3 text-sm text-slate-500 placeholder-slate-400 transition-colors focus:outline-none disabled:cursor-not-allowed dark:border-border dark:bg-white/[0.03] dark:text-ink-secondary dark:placeholder-ink-muted"
          />
        </div>

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
