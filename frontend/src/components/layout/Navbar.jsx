import { NavLink } from 'react-router-dom'

const links = [
  { to: '/', label: 'Home' },
  { to: '/chat', label: 'Chat' },
  { to: '/about', label: 'About' },
]

export default function Navbar() {
  return (
    <nav className="bg-white border-b border-gray-200">
      <div className="container mx-auto px-4 flex items-center justify-between h-16">
        <span className="font-bold text-lg text-indigo-600">InsightAI</span>
        <ul className="flex gap-6">
          {links.map(({ to, label }) => (
            <li key={to}>
              <NavLink
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  isActive
                    ? 'text-indigo-600 font-medium'
                    : 'text-gray-600 hover:text-indigo-600 transition-colors'
                }
              >
                {label}
              </NavLink>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  )
}
