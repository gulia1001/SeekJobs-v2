'use client'
import { useEffect, useState, type FormEvent } from 'react'
import { ApiError } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useI18n, type MessageKey } from '@/lib/i18n'

/** Turn an API error into a message in the user's language. */
function authErrorKey(e: unknown): MessageKey | null {
  if (!(e instanceof ApiError)) return null
  if (e.status === 401) return 'auth.err.wrong'
  if (e.status === 409) return 'auth.err.exists'
  if (e.status === 429) return 'auth.err.tooMany'
  if (e.status === 422) {
    if (e.message.includes('email')) return 'auth.err.email'
    if (e.message.includes('password')) return 'auth.err.password'
    if (e.message.includes('personal data')) return 'auth.err.consent'
  }
  if (e.status === 0) return 'ai.err.network'
  return null
}

export default function AuthModal() {
  const { t } = useI18n()
  const { loginOpen, closeLogin, login, register } = useAuth()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [consent, setConsent] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!loginOpen) return
    setError('')
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') closeLogin() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [loginOpen, closeLogin])

  if (!loginOpen) return null

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    if (mode === 'register' && !consent) { setError(t('auth.err.consent')); return }
    setBusy(true)
    try {
      if (mode === 'login') await login(email, password)
      else await register({ email, password, name, consent })
      setPassword('')
    } catch (err) {
      const key = authErrorKey(err)
      setError(key ? t(key) : t('auth.err.generic', { msg: err instanceof Error ? err.message : String(err) }))
    } finally {
      setBusy(false)
    }
  }

  const isLogin = mode === 'login'
  return (
    <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) closeLogin() }}>
      <div className="modal auth-modal" role="dialog" aria-modal="true" aria-labelledby="auth-title">
        <div className="modal-header">
          <div className="modal-title" id="auth-title">{isLogin ? t('auth.login') : t('auth.register')}</div>
          <button className="modal-close" onClick={closeLogin} aria-label={t('cv.close')}>✕</button>
        </div>
        <form className="modal-body auth-form" onSubmit={submit}>
          <label className="input-group">
            <span className="input-label">{t('auth.email')}</span>
            <input id="auth-email" className="ai-input" type="email" autoComplete="email" required
                   value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label className="input-group">
            <span className="input-label">{t('auth.password')}</span>
            <input id="auth-password" className="ai-input" type="password" required minLength={8}
                   autoComplete={isLogin ? 'current-password' : 'new-password'}
                   placeholder={isLogin ? '' : t('auth.passwordHint')}
                   value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          {!isLogin && (
            <>
              <label className="input-group">
                <span className="input-label">{t('auth.name')}</span>
                <input id="auth-name" className="ai-input" type="text" autoComplete="name" maxLength={120}
                       value={name} onChange={(e) => setName(e.target.value)} />
              </label>
              <label className="consent-row">
                <input id="auth-consent" type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
                <span>{t('auth.consent')} <a href="/privacy" target="_blank" rel="noopener noreferrer">{t('auth.privacyLink')}</a>.</span>
              </label>
            </>
          )}
          {error && <div className="form-error" role="alert">⚠ {error}</div>}
          <button className="analyze-btn" type="submit" disabled={busy}>
            {busy ? '…' : isLogin ? t('auth.login') : t('auth.register')}
          </button>
          <button type="button" className="link-btn" onClick={() => { setMode(isLogin ? 'register' : 'login'); setError('') }}>
            {isLogin ? t('auth.toRegister') : t('auth.toLogin')}
          </button>
        </form>
      </div>
    </div>
  )
}
