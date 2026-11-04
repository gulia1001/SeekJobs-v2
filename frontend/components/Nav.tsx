'use client'
import { useAuth } from '@/lib/auth'
import { LANGS, useI18n } from '@/lib/i18n'

export function Logo() {
  return (
    <>
      <span className="logo-dot" />
      Seek<em className="logo-em">Jobs</em>
    </>
  )
}

export default function Nav() {
  const { t, lang } = useI18n()
  const { user, ready, openLogin, logout, changeLanguage } = useAuth()

  return (
    <nav>
      <a className="logo" href="/"><Logo /></a>
      <ul className="nav-links">
        <li className="nav-text"><a href="/#jobs">{t('nav.vacancies')}</a></li>
        <li className="nav-text"><a href="/#ai-agent">{t('nav.match')}</a></li>
        {user && <li className="nav-text"><a href="/tracker">{t('nav.tracker')}</a></li>}
        {user && <li><a href="/account">{t('nav.account')}</a></li>}
        <li className="lang-switch" role="group" aria-label={t('nav.language')}>
          {LANGS.map((l) => (
            <button key={l.code} type="button" className={lang === l.code ? 'active' : ''}
                    aria-pressed={lang === l.code} onClick={() => changeLanguage(l.code)}>
              {l.label}
            </button>
          ))}
        </li>
        <li className={user ? 'nav-text' : ''}>
          {!ready ? null : user ? (
            <button type="button" className="nav-cta nav-btn" onClick={logout}>{t('nav.logout')}</button>
          ) : (
            <button type="button" className="nav-cta nav-btn" onClick={openLogin}>{t('nav.login')}</button>
          )}
        </li>
      </ul>
    </nav>
  )
}
