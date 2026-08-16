import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { authAPI } from '../api/auth'
import { setAuthToken, clearAuthToken } from '../api/axios'

const AuthContext = createContext(null)

function clearTokens() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
}

function storeSession(payload) {
  const { tokens, user } = payload
  localStorage.setItem('access_token', tokens.access)
  localStorage.setItem('refresh_token', tokens.refresh)
  setAuthToken(tokens.access)
  return user
}

export function AuthProvider({ children }) {
  const [user,    setUser]    = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    if (token) {
      setAuthToken(token)
      authAPI.getProfile()
        .then(res => setUser(res.data.data))
        .catch(() => { clearTokens(); clearAuthToken() })
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  // Accounts are identified by email — there is no username to type any more.
  const login = useCallback(async (email, password) => {
    const res = await authAPI.login({ email, password })
    const userData = storeSession(res.data.data)
    setUser(userData)
    return userData
  }, [])

  // Same credentials, but the endpoint refuses accounts without staff rights.
  const adminLogin = useCallback(async (email, password) => {
    const res = await authAPI.adminLogin({ email, password })
    const userData = storeSession(res.data.data)
    setUser(userData)
    return userData
  }, [])

  /** `credential` is the ID token handed over by Google Identity Services. */
  const googleLogin = useCallback(async (credential, { adminOnly = false } = {}) => {
    const res = await authAPI.google({ credential, admin_only: adminOnly })
    const data = res.data.data
    setUser(storeSession(data))
    return data
  }, [])

  // Step 1 of sign-up. No account and no session yet — this only asks the server
  // to email a verification code, and returns { email, expires_in_seconds,
  // resend_after_seconds } for the code screen to count down against.
  const register = useCallback(async (data) => {
    const res = await authAPI.register(data)
    return res.data.data
  }, [])

  const resendRegisterCode = useCallback(async (email) => {
    const res = await authAPI.registerResend({ email })
    return res.data.data
  }, [])

  // Step 2 creates the account and stores the session (tokens + auth header),
  // but intentionally does NOT set the user in state. RegisterPage shows an
  // animated success screen and then commits via setUser(), which is what flips
  // GuestRoute and navigates into the app — letting the animation actually play.
  const verifyRegistration = useCallback(async (email, code) => {
    const res = await authAPI.registerVerify({ email, code })
    const { tokens, user: userData } = res.data.data
    localStorage.setItem('access_token',  tokens.access)
    localStorage.setItem('refresh_token', tokens.refresh)
    setAuthToken(tokens.access)
    return userData
  }, [])

  const logout = useCallback(async () => {
    const refresh = localStorage.getItem('refresh_token')
    try { await authAPI.logout({ refresh }) } catch (_) {}
    clearTokens()
    clearAuthToken()
    setUser(null)
  }, [])

  const refreshUser = useCallback(async () => {
    const res = await authAPI.getProfile()
    setUser(res.data.data)
  }, [])

  return (
    <AuthContext.Provider
      value={{
        user, loading, login, adminLogin, googleLogin,
        register, resendRegisterCode, verifyRegistration,
        logout, refreshUser, setUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
