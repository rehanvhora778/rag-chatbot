import { useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import { loadGoogleScript, resolveGoogleClientId } from '../../lib/google'

/* ── Vendor glyphs (inline so nothing is fetched from a CDN) ───────────── */

function GoogleGlyph({ size = 17 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden>
      <path fill="#FFC107" d="M43.6 20.1H42V20H24v8h11.3C33.7 32.7 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 13 4 4 13 4 24s9 20 20 20 20-9 20-20c0-1.3-.1-2.6-.4-3.9z" />
      <path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.3 0-9.7-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.1H42V20H24v8h11.3c-.8 2.2-2.2 4.1-4.1 5.5l6.2 5.2C36.9 40.2 44 35 44 24c0-1.3-.1-2.6-.4-3.9z" />
    </svg>
  )
}

const SHELL =
  'relative flex h-11 w-full items-center justify-center gap-2.5 rounded-xl border border-white/10 ' +
  'bg-white/[0.03] text-sm font-medium text-zinc-200 transition-all duration-200 ' +
  'hover:border-primary-500/35 hover:bg-white/[0.06] disabled:cursor-not-allowed disabled:opacity-60'

/**
 * "Continue with Google".
 *
 * Google Identity Services will only emit an ID token from a button it renders
 * itself, so the real GSI button is mounted transparently on top of ours — the
 * user sees this design, Google sees its own click target.
 */
export function GoogleButton({ onCredential, disabled, label = 'Continue with Google' }) {
  const holder = useRef(null)
  const cbRef = useRef(onCredential)
  const [clientId, setClientId] = useState(null)   // null = still resolving, '' = not configured

  cbRef.current = onCredential

  useEffect(() => {
    let alive = true

    resolveGoogleClientId().then(id => {
      if (!alive) return
      setClientId(id)
      if (!id) return

      loadGoogleScript()
        .then(google => {
          if (!alive || !holder.current) return
          google.accounts.id.initialize({
            client_id: id,
            callback: res => cbRef.current?.(res.credential),
            ux_mode: 'popup',
          })
          const width = Math.min(400, Math.max(200, holder.current.offsetWidth || 320))
          holder.current.innerHTML = ''
          google.accounts.id.renderButton(holder.current, {
            type: 'standard',
            theme: 'filled_black',
            size: 'large',
            text: 'continue_with',
            shape: 'rectangular',
            logo_alignment: 'center',
            width,
          })
        })
        .catch(() => { if (alive) setClientId('') })
    })

    return () => { alive = false }
  }, [])

  const notConfigured = clientId === ''

  return (
    <div className="relative">
      <button
        type="button"
        className={SHELL}
        disabled={disabled}
        onClick={() =>
          notConfigured &&
          toast.error('Google sign-in is not configured yet — add GOOGLE_CLIENT_ID to backend/.env.')
        }
      >
        <GoogleGlyph /> {label}
      </button>

      {/* Google's own button: invisible, exactly on top, and only when usable */}
      {!notConfigured && !disabled && (
        <div
          ref={holder}
          className="absolute inset-0 overflow-hidden opacity-0"
          style={{ colorScheme: 'light' }}
          aria-hidden
        />
      )}
    </div>
  )
}

/** "or continue with" rule + the Google button — the only SSO provider here. */
export function SocialRow({ onCredential, disabled, label = 'or continue with' }) {
  return (
    <>
      <div className="my-4 flex items-center gap-3">
        <span className="h-px flex-1 bg-white/10" />
        <span className="text-xs font-medium text-zinc-500">{label}</span>
        <span className="h-px flex-1 bg-white/10" />
      </div>
      <GoogleButton onCredential={onCredential} disabled={disabled} />
    </>
  )
}
