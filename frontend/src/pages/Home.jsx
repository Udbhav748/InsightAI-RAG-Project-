import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowRight, FileText, MessageCircle, UploadCloud } from 'lucide-react'
import Card from '../components/ui/Card'
import Logo from '../components/ui/Logo'
import { getHealthStatus } from '../services/healthService'

const ACTIONS = [
  {
    to: '/upload',
    icon: UploadCloud,
    title: 'Upload a document',
    description: 'Add a PDF to your knowledge base in seconds.',
  },
  {
    to: '/chat',
    icon: MessageCircle,
    title: 'Start a conversation',
    description: 'Ask questions grounded in your documents.',
  },
  {
    to: '/documents',
    icon: FileText,
    title: 'Browse documents',
    description: 'Manage everything you’ve uploaded so far.',
  },
]

export default function Home() {
  const [status, setStatus] = useState('checking')
  const [provider, setProvider] = useState('')

  useEffect(() => {
    getHealthStatus()
      .then((health) => {
        setStatus('online')
        setProvider(health?.llm?.provider ?? '')
      })
      .catch(() => setStatus('offline'))
  }, [])

  return (
    <div className="flex flex-col items-center py-10 text-center sm:py-16">
      <motion.span
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl border border-border-light bg-slate-900/5 text-accent-600 dark:border-border dark:bg-white/[0.03] dark:text-accent-500"
      >
        <Logo size={24} />
      </motion.span>

      <motion.h1
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className="font-display text-3xl font-bold text-slate-900 dark:text-ink-primary sm:text-4xl"
      >
        InsightAI Document Intelligence
      </motion.h1>

      <motion.p
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="mt-3 max-w-md text-sm text-slate-500 dark:text-ink-muted"
      >
        Upload PDF documents and ask questions in natural language. Answers are grounded in your own content.
      </motion.p>

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.15 }}
        className="mt-6 inline-flex items-center gap-2 rounded-full border border-border-light bg-white/60 px-4 py-1.5 text-xs text-slate-500 dark:border-border dark:bg-white/[0.03] dark:text-ink-muted"
      >
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            status === 'online' ? 'bg-success' : status === 'offline' ? 'bg-danger' : 'bg-warning animate-pulse-soft'
          }`}
        />
        {status === 'checking' && 'Checking backend...'}
        {status === 'online' && (provider ? `Backend connected · ${provider}` : 'Backend connected')}
        {status === 'offline' && 'Backend unreachable'}
      </motion.div>

      <div className="mt-10 grid w-full max-w-3xl gap-4 sm:grid-cols-3">
        {ACTIONS.map(({ to, icon: Icon, title, description }) => (
          <Card key={to} as={Link} to={to} hover padding="lg" className="group flex flex-col items-start text-left">
            <span className="mb-4 flex h-9 w-9 items-center justify-center rounded-lg border border-border-light bg-slate-900/5 text-slate-500 dark:border-border dark:bg-white/[0.03] dark:text-ink-secondary">
              <Icon size={17} strokeWidth={1.5} />
            </span>
            <h3 className="font-display text-sm font-semibold text-slate-800 dark:text-ink-primary">{title}</h3>
            <p className="mt-1 text-xs text-slate-500 dark:text-ink-muted">{description}</p>
            <span className="mt-4 flex items-center gap-1 text-xs font-medium text-accent-600 opacity-0 transition-opacity group-hover:opacity-100 dark:text-accent-500">
              Get started <ArrowRight size={12} />
            </span>
          </Card>
        ))}
      </div>
    </div>
  )
}
