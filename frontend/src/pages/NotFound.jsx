import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <div className="text-center py-20">
      <h2 className="text-7xl font-bold text-gray-200">404</h2>
      <p className="text-gray-500 mt-4 mb-8 text-lg">Page not found.</p>
      <Link to="/" className="text-indigo-600 hover:underline font-medium">
        Go home
      </Link>
    </div>
  )
}
