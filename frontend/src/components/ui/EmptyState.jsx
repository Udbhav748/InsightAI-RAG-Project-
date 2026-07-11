import { motion } from 'framer-motion'

export default function EmptyState({ icon: Icon, title, description, action, className = '' }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className={`flex flex-col items-center justify-center rounded-3xl border border-dashed border-border-light py-16 text-center dark:border-border ${className}`}
    >
      {Icon && (
        <span className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-accent-500/10 text-accent-500 dark:text-accent-400">
          <Icon size={26} strokeWidth={1.75} />
        </span>
      )}
      {title && <h3 className="text-base font-semibold text-slate-800 dark:text-slate-100">{title}</h3>}
      {description && (
        <p className="mt-1.5 max-w-sm text-sm text-slate-500 dark:text-slate-400">{description}</p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </motion.div>
  )
}
