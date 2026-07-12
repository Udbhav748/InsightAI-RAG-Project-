import { useEffect } from 'react'
import { NavLink } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { FileText, MessageSquarePlus, Settings, Sparkles, UploadCloud, X } from 'lucide-react'
import ThemeToggle from '../ui/ThemeToggle'

const NAV_ITEMS = [
  { to: '/chat', label: 'New Chat', icon: MessageSquarePlus },
  { to: '/upload', label: 'Upload Document', icon: UploadCloud },
  { to: '/documents', label: 'Documents', icon: FileText },
]

function SidebarContent({ onNavigate }) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2.5 px-5 pb-6 pt-6">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-accent-500 to-accent-glow text-white shadow-glow-sm">
          <Sparkles size={18} strokeWidth={2.25} />
        </span>
        <div className="leading-tight">
          <p className="font-display text-sm font-bold text-slate-900 dark:text-white">InsightAI</p>
          <p className="text-[11px] text-slate-400 dark:text-slate-500">Document Intelligence</p>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            onClick={onNavigate}
            className={({ isActive }) =>
              `group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200 ${
                isActive
                  ? 'bg-gradient-to-r from-accent-500/15 to-accent-glow/10 text-accent-600 shadow-[inset_0_0_0_1px_rgba(56,200,251,0.25)] dark:text-accent-300'
                  : 'text-slate-500 hover:bg-slate-900/5 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-white/5 dark:hover:text-slate-100'
              }`
            }
          >
            <Icon size={17} strokeWidth={2} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="space-y-1 border-t border-border-light px-3 pb-5 pt-3 dark:border-border">
        <NavLink
          to="/settings"
          onClick={onNavigate}
          className={({ isActive }) =>
            `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200 ${
              isActive
                ? 'bg-slate-900/5 text-slate-900 dark:bg-white/10 dark:text-white'
                : 'text-slate-500 hover:bg-slate-900/5 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-white/5 dark:hover:text-slate-100'
            }`
          }
        >
          <Settings size={17} strokeWidth={2} />
          Settings
        </NavLink>
        <div className="flex items-center justify-between rounded-xl px-3 py-2 text-sm text-slate-500 dark:text-slate-400">
          Appearance
          <ThemeToggle />
        </div>
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
      <aside className="glass-panel sticky top-4 hidden h-[calc(100vh-2rem)] w-64 shrink-0 rounded-3xl lg:block">
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
              className="fixed inset-0 z-40 bg-slate-950/50 backdrop-blur-sm lg:hidden"
              onClick={onClose}
            />
            <motion.aside
              initial={{ x: '-100%' }}
              animate={{ x: 0 }}
              exit={{ x: '-100%' }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              className="glass-panel fixed inset-y-4 left-4 z-50 w-64 rounded-3xl lg:hidden"
            >
              <button
                type="button"
                onClick={onClose}
                aria-label="Close menu"
                className="absolute right-4 top-5 rounded-lg p-1.5 text-slate-400 hover:bg-slate-900/5 hover:text-slate-700 dark:hover:bg-white/10 dark:hover:text-white"
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
