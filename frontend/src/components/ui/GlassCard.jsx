import { useMemo } from 'react'
import { motion } from 'framer-motion'

const PADDING = {
  none: '',
  sm: 'p-4',
  md: 'p-6',
  lg: 'p-8',
}

export default function GlassCard({
  as = 'div',
  hover = false,
  padding = 'md',
  className = '',
  children,
  ...props
}) {
  // Wrap whatever `as` is (a DOM tag, react-router's Link, etc.) so it
  // gains Framer Motion props, without letting motion() run on every
  // render — that would create a new component type each time and
  // remount the node.
  const MotionComponent = useMemo(() => motion(as), [as])

  return (
    <MotionComponent
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
      className={`glass-panel ${PADDING[padding]} ${hover ? 'panel-hover' : ''} ${className}`}
      {...props}
    >
      {children}
    </MotionComponent>
  )
}
