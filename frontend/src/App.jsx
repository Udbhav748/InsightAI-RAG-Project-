import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import AppLayout from './layouts/AppLayout'
import Skeleton from './components/ui/Skeleton'
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

// Used both as the pre-auth full-page fallback (ProtectedRoute, no app
// chrome around it yet) and as the per-route Suspense fallback inside
// AppLayout (sidebar/navbar already visible) — a generic content-shaped
// skeleton reads reasonably in either context, unlike a spinner floating
// alone in whichever of those two layouts it happens to land in.
function PageFallback() {
  return (
    <div className="mx-auto max-w-2xl space-y-5 py-4">
      <div className="space-y-2">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-3.5 w-64" />
      </div>
      <Skeleton className="h-32 w-full rounded-panel" />
      <Skeleton className="h-32 w-full rounded-panel" />
    </div>
  )
}

function Page({ children }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
    >
      <Suspense fallback={<PageFallback />}>{children}</Suspense>
    </motion.div>
  )
}

function AnimatedRoutes() {
  const location = useLocation()

  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        <Route
          path="/login"
          element={
            <Page>
              <Login />
            </Page>
          }
        />
        <Route
          path="/signup"
          element={
            <Page>
              <Signup />
            </Page>
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
          <Route
            index
            element={
              <Page>
                <Home />
              </Page>
            }
          />
          <Route
            path="chat"
            element={
              <Page>
                {/* location.key changes on every navigation, even to the same
                    path, so clicking "New Chat" while already on /chat
                    remounts the page and starts a fresh conversation. */}
                <Chat key={location.key} />
              </Page>
            }
          />
          <Route
            path="upload"
            element={
              <Page>
                <Upload />
              </Page>
            }
          />
          <Route
            path="diagnose"
            element={
              <Page>
                <Diagnose />
              </Page>
            }
          />
          <Route
            path="documents"
            element={
              <Page>
                <Documents />
              </Page>
            }
          />
          <Route
            path="history"
            element={
              <Page>
                <History />
              </Page>
            }
          />
          <Route
            path="settings"
            element={
              <Page>
                <Settings />
              </Page>
            }
          />
          <Route
            path="*"
            element={
              <Page>
                <NotFound />
              </Page>
            }
          />
        </Route>
      </Routes>
    </AnimatePresence>
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
