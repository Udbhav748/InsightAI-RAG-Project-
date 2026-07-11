import { lazy, Suspense } from 'react'
import { BrowserRouter, Route, Routes, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import AppLayout from './layouts/AppLayout'
import LoadingSpinner from './components/ui/LoadingSpinner'
import ThemeProvider from './contexts/ThemeContext'
import ToastProvider from './contexts/ToastContext'

const Home = lazy(() => import('./pages/Home'))
const Chat = lazy(() => import('./pages/Chat'))
const Upload = lazy(() => import('./pages/Upload'))
const Documents = lazy(() => import('./pages/Documents'))
const Settings = lazy(() => import('./pages/Settings'))
const NotFound = lazy(() => import('./pages/NotFound'))

function PageFallback() {
  return (
    <div className="flex h-64 items-center justify-center">
      <LoadingSpinner size="lg" />
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
        <Route path="/" element={<AppLayout />}>
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
            path="documents"
            element={
              <Page>
                <Documents />
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
          <AnimatedRoutes />
        </BrowserRouter>
      </ToastProvider>
    </ThemeProvider>
  )
}
