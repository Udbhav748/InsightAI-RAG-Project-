import React from 'react'
import LoadingSpinner from './LoadingSpinner'

export default function LoadingState({ 
  message = 'Loading...', 
  submessage = '',
  size = 'md' 
}) {
  return (
    <div className="flex flex-col items-center justify-center p-8">
      <LoadingSpinner size={size} text={message} />
      {submessage && (
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
          {submessage}
        </p>
      )}
    </div>
  )
}
