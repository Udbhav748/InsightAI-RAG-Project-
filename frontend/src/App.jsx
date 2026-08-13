import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'
import AppLayout from './layouts/AppLayout'
import PageFallback from './components/ui/PageFallback'
import ThemeProvider from './contexts/ThemeContext'
import ToastProvider from './contexts/ToastContext'
import AuthProvider from './contexts/AuthContext'
import useAuth from './hooks/useAuth'

const Home = lazy(() => import('./pages/Home'))
const Chat = lazy(() => import('./pages/Chat'))
const Diagnose = lazy(() => import('./pages/Diagnose'))
const Upload = lazy(() => import('./pages/Upload'))
const Documents = lazy(() => import('./pages/Documents'))
const History = lazy(() => import('./pages/History'))
const Settings = lazy(() => import('./pages/Settings'))
const Login = lazy(() => import('./pages/Login'))
const Signup = lazy(() => import('./pages/Signup'))
const NotFound = lazy(() => import('./pages/NotFound'))

function ProtectedRoute({ children }) {
  const { isAuthenticated, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) return <PageFallback />
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return children
}

// Login/Signup live outside AppLayout (no sidebar/navbar yet), so each
// still needs its own Suspense + entrance fade. Unlike the authenticated
// routes below, there's no AnimatePresence here — an exit-fade between the
// two is a minor nicety not worth the extra machinery of a second sibling
// <Routes> tree just to preserve it.
function AuthPage({ children }) {
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
      <Suspense fallback={<PageFallback />}>{children}</Suspense>
    </motion.div>
  )
}

function AnimatedRoutes() {
  const location = useLocation()

  return (
    <Routes location={location}>
      <Route
        path="/login"
        element={
          <AuthPage>
            <Login />
          </AuthPage>
        }
      />
      <Route
        path="/signup"
        element={
          <AuthPage>
            <Signup />
          </AuthPage>
        }
      />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Home />} />
        {/* location.key changes on every navigation, even to the same path,
            so clicking "New Chat" while already on /chat remounts the page
            and starts a fresh conversation. */}
        <Route path="chat" element={<Chat key={location.key} />} />
        <Route path="upload" element={<Upload />} />
        <Route path="diagnose" element={<Diagnose />} />
        <Route path="documents" element={<Documents />} />
        <Route path="history" element={<History />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <ToastProvider>
        <BrowserRouter>
          <AuthProvider>
            <AnimatedRoutes />
          </AuthProvider>
        </BrowserRouter>
      </ToastProvider>
    </ThemeProvider>
  )
}
