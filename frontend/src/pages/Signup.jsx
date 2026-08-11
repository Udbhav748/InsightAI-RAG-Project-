import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Sparkles, UserPlus } from 'lucide-react'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import useAuth from '../hooks/useAuth'
import getErrorMessage from '../utils/errorMessage'

export default function Signup() {
  const { signup } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [consent, setConsent] = useState(false)
  const [error, setError] = useState(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)

    if (!consent) {
      setError('You must agree to how your account data is stored to sign up.')
      return
    }

    setIsSubmitting(true)
    try {
      await signup(email, password, consent)
      navigate('/chat', { replace: true })
    } catch (err) {
      setError(getErrorMessage(err, 'Could not create your account.'))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center text-center">
          <span className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl border border-border-light bg-slate-900/5 text-accent-600 dark:border-border dark:bg-white/[0.03] dark:text-accent-500">
            <Sparkles size={20} strokeWidth={1.5} />
          </span>
          <h1 className="font-display text-xl font-bold text-slate-900 dark:text-ink-primary">Create your account</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-ink-muted">
            Your documents and chat history are private to you.
          </p>
        </div>

        <Card padding="lg">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="email" className="mb-1.5 block text-xs font-medium text-slate-600 dark:text-ink-secondary">
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                autoComplete="email"
                className="input"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </div>
            <div>
              <label
                htmlFor="password"
                className="mb-1.5 block text-xs font-medium text-slate-600 dark:text-ink-secondary"
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                required
                minLength={8}
                autoComplete="new-password"
                className="input"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              <p className="mt-1 text-[11px] text-slate-400 dark:text-ink-muted">At least 8 characters.</p>
            </div>

            <label className="flex items-start gap-2 text-xs text-slate-500 dark:text-ink-muted">
              <input
                type="checkbox"
                className="mt-0.5 h-3.5 w-3.5 rounded border-border-light dark:border-border"
                checked={consent}
                onChange={(event) => setConsent(event.target.checked)}
              />
              I agree that my email and password (hashed, never stored in plain text) are stored to create
              and secure my account.
            </label>

            {error && <p className="text-xs text-danger">{error}</p>}

            <Button
              type="submit"
              variant="primary"
              size="md"
              icon={UserPlus}
              loading={isSubmitting}
              className="w-full"
            >
              Sign up
            </Button>
          </form>
        </Card>

        <p className="mt-5 text-center text-sm text-slate-500 dark:text-ink-muted">
          Already have an account?{' '}
          <Link to="/login" className="font-medium text-accent-600 dark:text-accent-500">
            Log in
          </Link>
        </p>
      </motion.div>
    </div>
  )
}
