import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowRight, FileText, MessageCircle, Sparkles, UploadCloud } from 'lucide-react'
import GlassCard from '../components/ui/GlassCard'
import api from '../services/api'

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

  useEffect(() => {
    api
      .get('/health')
      .then(() => setStatus('online'))
      .catch(() => setStatus('offline'))
  }, [])

  return (
    <div className="flex flex-col items-center py-10 text-center sm:py-16">
      <motion.span
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-accent-500 to-accent-glow text-white shadow-glow animate-float"
      >
        <Sparkles size={26} />
      </motion.span>

      <motion.h1
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className="font-display text-3xl font-bold sm:text-4xl"
      >
        <span className="text-gradient">InsightAI</span> Document Intelligence
      </motion.h1>

      <motion.p
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="mt-3 max-w-md text-sm text-slate-500 dark:text-slate-400"
      >
        Upload PDF documents and ask questions in natural language. Answers are grounded in your own content.
      </motion.p>

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.15 }}
        className="mt-6 inline-flex items-center gap-2 rounded-full border border-border-light bg-white/60 px-4 py-1.5 text-xs text-slate-500 backdrop-blur dark:border-border dark:bg-white/5 dark:text-slate-400"
      >
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            status === 'online' ? 'bg-emerald-400' : status === 'offline' ? 'bg-rose-400' : 'bg-amber-400 animate-pulse-glow'
          }`}
        />
        {status === 'checking' && 'Checking backend...'}
        {status === 'online' && 'Backend connected'}
        {status === 'offline' && 'Backend unreachable'}
      </motion.div>

      <div className="mt-10 grid w-full max-w-3xl gap-4 sm:grid-cols-3">
        {ACTIONS.map(({ to, icon: Icon, title, description }, index) => (
          <GlassCard
            key={to}
            as={Link}
            to={to}
            hover
            padding="lg"
            className="group flex flex-col items-start text-left"
            style={{ transitionDelay: `${index * 40}ms` }}
          >
            <span className="mb-4 flex h-10 w-10 items-center justify-center rounded-xl bg-accent-500/10 text-accent-500 dark:text-accent-400">
              <Icon size={19} strokeWidth={1.75} />
            </span>
            <h3 className="font-display text-sm font-semibold text-slate-800 dark:text-slate-100">{title}</h3>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{description}</p>
            <span className="mt-4 flex items-center gap-1 text-xs font-medium text-accent-600 opacity-0 transition-opacity group-hover:opacity-100 dark:text-accent-400">
              Get started <ArrowRight size={12} />
            </span>
          </GlassCard>
        ))}
      </div>
    </div>
  )
}
