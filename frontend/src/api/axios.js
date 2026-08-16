import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  headers: { 'Content-Type': 'application/json' },
  timeout: 120000,  // 2 minutes (LLM calls can be slow)
})

export function setAuthToken(token) {
  api.defaults.headers.common['Authorization'] = `Bearer ${token}`
}

export function clearAuthToken() {
  delete api.defaults.headers.common['Authorization']
}

// Auto-refresh JWT on 401
let isRefreshing = false
let failedQueue = []

const processQueue = (error, token = null) => {
  failedQueue.forEach(p => error ? p.reject(error) : p.resolve(token))
  failedQueue = []
}

api.interceptors.response.use(
  res => res,
  async error => {
    const original = error.config
    if (error.response?.status === 401 && !original._retry) {
      // Don't intercept 401s from the sign-in endpoints themselves — those are
      // "wrong credentials", not "expired session"; let the caller handle them.
      const SIGN_IN_PATHS = ['/api/auth/login/', '/api/auth/admin/login/', '/api/auth/google/', '/api/auth/register/']
      if (SIGN_IN_PATHS.some(p => original.url?.includes(p))) {
        return Promise.reject(error)
      }

      const refresh = localStorage.getItem('refresh_token')
      if (!refresh) {
        window.location.href = '/login'
        return Promise.reject(error)
      }

      if (isRefreshing) {
        return new Promise((resolve, reject) => failedQueue.push({ resolve, reject }))
          .then(token => { original.headers['Authorization'] = `Bearer ${token}`; return api(original) })
          .catch(e => Promise.reject(e))
      }

      original._retry = true
      isRefreshing = true

      try {
        const res = await axios.post(
          `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/api/auth/token/refresh/`,
          { refresh },
        )
        const newToken = res.data.data.access
        localStorage.setItem('access_token', newToken)
        setAuthToken(newToken)
        processQueue(null, newToken)
        original.headers['Authorization'] = `Bearer ${newToken}`
        return api(original)
      } catch (e) {
        processQueue(e, null)
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        clearAuthToken()
        window.location.href = '/login'
        return Promise.reject(e)
      } finally {
        isRefreshing = false
      }
    }
    return Promise.reject(error)
  }
)

export default api
