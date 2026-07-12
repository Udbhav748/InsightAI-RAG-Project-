import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from '../components/layout/Sidebar'
import Navbar from '../components/layout/Navbar'

export default function AppLayout() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  return (
    <div className="min-h-screen bg-surface-light bg-fixed dark:bg-grid-glow">
      <div className="mx-auto flex max-w-[1400px] gap-4 p-4">
        <Sidebar isOpen={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />

        <div className="flex min-w-0 flex-1 flex-col gap-4">
          <Navbar onMenuClick={() => setMobileNavOpen(true)} />
          <main className="min-w-0 flex-1 pb-4">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  )
}
