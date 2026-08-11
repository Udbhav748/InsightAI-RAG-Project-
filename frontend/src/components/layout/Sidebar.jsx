import { useEffect } from 'react'
import { NavLink } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Camera,
  FileText,
  History,
  LogOut,
  MessageSquarePlus,
  Settings,
  Sparkles,
  UploadCloud,
  X,
} from 'lucide-react'
import ThemeToggle from '../ui/ThemeToggle'
import useAuth from '../../hooks/useAuth'

const NAV_ITEMS = [
  { to: '/chat', label: 'New Chat', icon: MessageSquarePlus },
  { to: '/history', label: 'History', icon: History },
  { to: '/diagnose', label: 'Leaf Diagnosis', icon: Camera },
  { to: '/upload', label: 'Upload Document', icon: UploadCloud },
  { to: '/documents', label: 'Documents', icon: FileText },
]

const navItemClass = ({ isActive }) =>
  `group flex items-center gap-3 rounded-lg border-l-2 py-2.5 pl-[10px] pr-3 text-sm font-medium transition-all duration-200 ${
    isActive
      ? 'border-accent-500 bg-slate-900/5 text-slate-900 dark:bg-white/[0.04] dark:text-ink-primary'
      : 'border-transparent text-slate-500 hover:bg-slate-900/5 hover:text-slate-800 dark:text-ink-muted dark:hover:bg-white/[0.03] dark:hover:text-ink-secondary'
  }`

function SidebarContent({ onNavigate }) {
  const { user, logout } = useAuth()

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2.5 px-5 pb-6 pt-6">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-border-light bg-slate-900/5 text-accent-600 dark:border-border dark:bg-white/[0.03] dark:text-accent-500">
          <Sparkles size={16} strokeWidth={1.75} />
        </span>
        <div className="leading-tight">
          <p className="font-display text-sm font-semibold text-slate-900 dark:text-ink-primary">InsightAI</p>
          <p className="text-[11px] text-slate-400 dark:text-ink-muted">Document Intelligence</p>
        </div>
      </div>

      <nav className="flex-1 space-y-0.5 px-3">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} onClick={onNavigate} className={navItemClass}>
            <Icon size={17} strokeWidth={1.75} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="space-y-0.5 border-t border-border-light px-3 pb-5 pt-3 dark:border-border">
        <NavLink to="/settings" onClick={onNavigate} className={navItemClass}>
          <Settings size={17} strokeWidth={1.75} />
          Settings
        </NavLink>
        <div className="flex items-center justify-between rounded-lg py-2 pl-[10px] pr-3 text-sm text-slate-500 dark:text-ink-muted">
          Appearance
          <ThemeToggle />
        </div>
        {user && (
          <button
            type="button"
            onClick={logout}
            className="flex w-full items-center gap-3 rounded-lg py-2.5 pl-[10px] pr-3 text-sm font-medium text-slate-500 transition-colors hover:bg-slate-900/5 hover:text-slate-800 dark:text-ink-muted dark:hover:bg-white/[0.03] dark:hover:text-ink-secondary"
          >
            <LogOut size={17} strokeWidth={1.75} />
            <span className="truncate">{user.email}</span>
          </button>
        )}
      </div>
    </div>
  )
}

export default function Sidebar({ isOpen, onClose }) {
  useEffect(() => {
    if (!isOpen) return undefined
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') onClose?.()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  return (
    <>
      {/* Desktop: static column */}
      <aside className="glass-panel sticky top-4 hidden h-[calc(100vh-2rem)] w-64 shrink-0 lg:block">
        <SidebarContent />
      </aside>

      {/* Mobile: off-canvas drawer */}
      <AnimatePresence>
        {isOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="fixed inset-0 z-40 bg-slate-950/60 backdrop-blur-sm lg:hidden"
              onClick={onClose}
            />
            <motion.aside
              initial={{ x: '-100%' }}
              animate={{ x: 0 }}
              exit={{ x: '-100%' }}
              transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
              className="glass-panel fixed inset-y-4 left-4 z-50 w-64 lg:hidden"
            >
              <button
                type="button"
                onClick={onClose}
                aria-label="Close menu"
                className="absolute right-4 top-5 rounded-lg p-1.5 text-slate-400 hover:bg-slate-900/5 hover:text-slate-700 dark:text-ink-muted dark:hover:bg-white/[0.05] dark:hover:text-ink-primary"
              >
                <X size={16} />
              </button>
              <SidebarContent onNavigate={onClose} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  )
}
