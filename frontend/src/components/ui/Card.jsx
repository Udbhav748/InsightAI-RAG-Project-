const PADDING = {
  none: '',
  sm: 'p-4',
  md: 'p-5',
  lg: 'p-7',
}

export default function Card({ padding = 'md', hover = false, className = '', children, ...props }) {
  return (
    <div
      className={`rounded-3xl border border-border-light bg-white/80 dark:border-white/5 dark:bg-white/[0.03]
        ${PADDING[padding]}
        ${hover ? 'transition-colors duration-200 hover:bg-white dark:hover:bg-white/[0.06]' : ''}
        ${className}`}
      {...props}
    >
      {children}
    </div>
  )
}
