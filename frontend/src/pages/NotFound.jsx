import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Compass, Home } from 'lucide-react'
import Button from '../components/ui/Button'

export default function NotFound() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col items-center justify-center py-20 text-center"
    >
      <span className="mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-accent-500/10 text-accent-500 dark:text-accent-400">
        <Compass size={28} strokeWidth={1.75} />
      </span>
      <h2 className="font-display text-6xl font-bold text-slate-200 dark:text-white/10">404</h2>
      <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">
        This page doesn't exist, or it may have moved.
      </p>
      <Button as={Link} to="/" variant="primary" icon={Home} className="mt-6">
        Back home
      </Button>
    </motion.div>
  )
}
