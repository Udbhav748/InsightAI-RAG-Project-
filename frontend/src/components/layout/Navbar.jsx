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
    <header className="glass-panel sticky top-4 z-30 flex items-center gap-4 rounded-3xl px-4 py-3 sm:px-6">
      <button
        type="button"
        onClick={onMenuClick}
        aria-label="Open menu"
        className="rounded-xl p-2 text-slate-500 hover:bg-slate-900/5 hover:text-slate-800 dark:text-slate-300 dark:hover:bg-white/10 lg:hidden"
      >
        <Menu size={18} />
      </button>

      <h1 className="font-display text-base font-semibold text-slate-900 dark:text-white sm:text-lg">
        {title}
      </h1>

      <div className="ml-auto flex items-center gap-3">
        <div className="relative hidden sm:block">
          <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search..."
            disabled
            className="h-9 w-48 rounded-xl border border-border-light bg-white/50 pl-9 pr-3 text-sm text-slate-500 placeholder-slate-400 backdrop-blur transition-colors focus:outline-none disabled:cursor-not-allowed dark:border-border dark:bg-white/5 dark:text-slate-400"
          />
        </div>

        <button
          type="button"
          aria-label="Profile"
          className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-slate-200 to-slate-300 text-slate-600 transition-transform hover:scale-105 dark:from-white/10 dark:to-white/5 dark:text-slate-300"
        >
          <User size={16} strokeWidth={2.25} />
        </button>
      </div>
    </header>
  )
}
