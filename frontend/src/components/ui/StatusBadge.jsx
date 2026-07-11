import { CheckCircle2, Clock, Loader2, XCircle } from 'lucide-react'

const STATUS_MAP = {
  uploaded: { label: 'Uploaded', icon: Clock, className: 'bg-slate-500/10 text-slate-500 dark:text-slate-400' },
  processing: {
    label: 'Processing',
    icon: Loader2,
    className: 'bg-accent-500/10 text-accent-600 dark:text-accent-400',
    spin: true,
  },
  processed: {
    label: 'Processed',
    icon: CheckCircle2,
    className: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  },
  failed: { label: 'Failed', icon: XCircle, className: 'bg-rose-500/10 text-rose-600 dark:text-rose-400' },
}

export default function StatusBadge({ status = 'uploaded', className = '' }) {
  const config = STATUS_MAP[status] ?? STATUS_MAP.uploaded
  const Icon = config.icon

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${config.className} ${className}`}
    >
      <Icon size={12} className={config.spin ? 'animate-spin' : ''} strokeWidth={2.5} />
      {config.label}
    </span>
  )
}
