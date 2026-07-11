import { Loader2 } from 'lucide-react'

const SIZES = { sm: 14, md: 20, lg: 28 }

export default function LoadingSpinner({ size = 'md', className = '' }) {
  return (
    <Loader2
      size={SIZES[size] ?? SIZES.md}
      className={`animate-spin text-accent-500 dark:text-accent-400 ${className}`}
      strokeWidth={2.5}
    />
  )
}
