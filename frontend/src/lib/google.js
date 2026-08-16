import api from '../api/axios'

const GSI_SRC = 'https://accounts.google.com/gsi/client'

let scriptPromise = null
let clientIdPromise = null

/** Loads Google Identity Services once, no matter how many buttons ask for it. */
export function loadGoogleScript() {
  if (window.google?.accounts?.id) return Promise.resolve(window.google)
  if (scriptPromise) return scriptPromise

  scriptPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${GSI_SRC}"]`)
    const el = existing || document.createElement('script')
    el.addEventListener('load', () => resolve(window.google))
    el.addEventListener('error', () => {
      scriptPromise = null
      reject(new Error('Could not load Google Sign-In.'))
    })
    if (!existing) {
      el.src = GSI_SRC
      el.async = true
      el.defer = true
      document.head.appendChild(el)
    }
  })
  return scriptPromise
}

/**
 * The OAuth client id, from the frontend env if present, otherwise from the
 * backend so only `backend/.env` has to be filled in. Resolves to '' when
 * Google sign-in is not configured — callers then show a hint instead.
 */
export function resolveGoogleClientId() {
  if (clientIdPromise) return clientIdPromise

  const fromEnv = (import.meta.env.VITE_GOOGLE_CLIENT_ID || '').trim()
  if (fromEnv) {
    clientIdPromise = Promise.resolve(fromEnv)
    return clientIdPromise
  }

  clientIdPromise = api
    .get('/api/auth/google/config/')
    .then(res => res.data?.data?.client_id || '')
    .catch(() => '')
  return clientIdPromise
}
