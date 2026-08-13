import { useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from '../components/layout/Sidebar'
import Navbar from '../components/layout/Navbar'
import CommandPalette from '../components/command/CommandPalette'

export default function AppLayout() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false)

  // Global Cmd/Ctrl+K — mounted here (not per-page) so it works from
  // anywhere in the authenticated app, not just whichever page happens to
  // render it. metaKey covers Mac; ctrlKey covers Windows/Linux.
  useEffect(() => {
    const handleKeyDown = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setCommandPaletteOpen((open) => !open)
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [])

  return (
    <div className="min-h-screen bg-surface-light dark:bg-surface-dark print:!bg-white">
      <div className="mx-auto flex max-w-[1400px] gap-4 p-4">
        <Sidebar isOpen={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />

        <div className="flex min-w-0 flex-1 flex-col gap-4">
          <Navbar onMenuClick={() => setMobileNavOpen(true)} onSearchClick={() => setCommandPaletteOpen(true)} />
          <main className="min-w-0 flex-1 pb-4 print:pb-0">
            <Outlet />
          </main>
        </div>
      </div>

      <CommandPalette open={commandPaletteOpen} onClose={() => setCommandPaletteOpen(false)} />
    </div>
  )
}
