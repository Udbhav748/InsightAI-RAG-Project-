import { useCallback, useEffect, useState } from 'react'
import { getMe, login as loginRequest, signup as signupRequest } from '../services/authService'
import { AUTH_TOKEN_KEY } from '../services/api'
import { AuthContext } from './auth-context'

export default function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  // isLoading covers the one-time "do we already have a valid token"
  // check on first load — kept separate from isAuthenticated so a
  // protected route can show a spinner instead of bouncing to /login
  // for a split second before that check resolves.
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const token = window.localStorage.getItem(AUTH_TOKEN_KEY)
    if (!token) {
      setIsLoading(false)
      return
    }
    getMe()
      .then(setUser)
      .catch(() => {
        // Token rejected (expired/invalid) — api.js's 401 interceptor
        // already clears it and redirects; nothing more to do here.
      })
      .finally(() => setIsLoading(false))
  }, [])

  const login = useCallback(async (email, password) => {
    const { access_token } = await loginRequest(email, password)
    window.localStorage.setItem(AUTH_TOKEN_KEY, access_token)
    const me = await getMe()
    setUser(me)
    return me
  }, [])

  const signup = useCallback(async (email, password, consent) => {
    const { access_token } = await signupRequest(email, password, consent)
    window.localStorage.setItem(AUTH_TOKEN_KEY, access_token)
    const me = await getMe()
    setUser(me)
    return me
  }, [])

  const logout = useCallback(() => {
    window.localStorage.removeItem(AUTH_TOKEN_KEY)
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider
      value={{ user, isAuthenticated: Boolean(user), isLoading, login, signup, logout }}
    >
      {children}
    </AuthContext.Provider>
  )
}
