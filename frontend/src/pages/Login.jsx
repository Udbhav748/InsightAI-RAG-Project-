import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { LogIn } from 'lucide-react'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import Logo from '../components/ui/Logo'
import useAuth from '../hooks/useAuth'
import getErrorMessage from '../utils/errorMessage'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const redirectTo = location.state?.from ?? '/chat'

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setIsSubmitting(true)
    try {
      await login(email, password)
      navigate(redirectTo, { replace: true })
    } catch (err) {
      setError(getErrorMessage(err, 'Could not log in. Check your email and password.'))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center text-center">
          <span className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl border border-border-light bg-slate-900/5 text-accent-600 dark:border-border dark:bg-white/[0.03] dark:text-accent-500">
            <Logo size={22} />
          </span>
          <h1 className="font-display text-xl font-bold text-slate-900 dark:text-ink-primary">Welcome back</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-ink-muted">Log in to InsightAI</p>
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
                autoComplete="current-password"
                className="input"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>

            {error && <p className="text-xs text-danger">{error}</p>}

            <Button type="submit" variant="primary" size="md" icon={LogIn} loading={isSubmitting} className="w-full">
              Log in
            </Button>
          </form>
        </Card>

        <p className="mt-5 text-center text-sm text-slate-500 dark:text-ink-muted">
          Don&apos;t have an account?{' '}
          <Link to="/signup" className="font-medium text-accent-600 dark:text-accent-500">
            Sign up
          </Link>
        </p>
      </motion.div>
    </div>
  )
}
