import React from 'react'
import { AlertCircle, XCircle } from 'lucide-react'

export default function ErrorMessage({ 
  error, 
  onRetry, 
  retryText = 'Try Again',
  className = '' 
}) {
  if (!error) return null

  const getErrorInfo = (err) => {
    if (typeof err === 'string') {
      return { message: err, code: null }
    }
    
    if (err?.response?.data) {
      return {
        message: err.response.data.detail || err.response.data.message || 'An error occurred',
        code: err.response.data.error_code || err.response.status
      }
    }
    
    if (err?.message) {
      return { message: err.message, code: null }
    }
    
    return { message: 'An unexpected error occurred', code: null }
  }

  const errorInfo = getErrorInfo(error)

  return (
    <div className={`rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20 ${className}`}>
      <div className="flex items-start">
        <div className="flex-shrink-0">
          <XCircle className="h-5 w-5 text-red-600 dark:text-red-400" />
        </div>
        
        <div className="ml-3 flex-1">
          <h4 className="text-sm font-medium text-red-800 dark:text-red-200">
            Error Occurred
          </h4>
          
          <div className="mt-1 text-sm text-red-700 dark:text-red-300">
            <p>{errorInfo.message}</p>
            {errorInfo.code && (
              <p className="mt-1">
                <span className="font-medium">Error Code:</span> {errorInfo.code}
              </p>
            )}
          </div>
          
          {onRetry && (
            <button
              onClick={onRetry}
              className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-red-800 hover:text-red-900 dark:text-red-200 dark:hover:text-red-100"
            >
              <AlertCircle className="h-4 w-4" />
              {retryText}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
