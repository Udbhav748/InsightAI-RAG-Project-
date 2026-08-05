import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 10000,
  headers: {
    'X-API-Key': import.meta.env.VITE_API_KEY,
  },
})

export default api
