'use client'
import { useEffect, useState } from 'react'
import Footer from '@/components/Footer'
import MatchCard from '@/components/MatchCard'
import Nav from '@/components/Nav'
import { ApiError, deleteMe, getMyMatches, telegramLink, telegramUnlink } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { formatTenge, usePostedAgo, useI18n, type MessageKey } from '@/lib/i18n'
import type { Match } from '@/lib/types'
import { useSavedJobs } from '@/lib/useSavedJobs'

function TodaysMatches() {
  const { t } = useI18n()
  const { savedIds, save } = useSavedJobs()
  const [matches, setMatches] = useState<Match[] | null>(null)

  useEffect(() => {
    getMyMatches()
      .then((r) => setMatches(Object.values(r.by_role).flatMap((g) => g.matches)
        .sort((a, b) => b.score - a.score).slice(0, 5)))
      .catch(() => setMatches([]))
  }, [])

  return (
    <section className="account-card">
      <h2 className="account-card-title">{t('account.matchesTitle')}</h2>
      {matches === null ? <div className="loading-spinner" />
        : matches.length === 0 ? <p className="muted">{t('account.noMatches')}</p>
          : matches.map((m, i) => (
            <MatchCard key={m.job.id} match={{ ...m, rank: i + 1 }} saved={savedIds.has(m.job.id)} onSave={save} />
          ))}
    </section>
  )
}

function TelegramCard() {
  const { t } = useI18n()
  const { me, refresh } = useAuth()
  const [link, setLink] = useState('')
  const [unavailable, setUnavailable] = useState(false)
  const linked = me?.telegram.linked

  const connect = async () => {
    try {
      const { url } = await telegramLink()
      setLink(url)
      window.open(url, '_blank', 'noopener')
    } catch (e) {
      if (e instanceof ApiError && e.status === 503) setUnavailable(true)
    }
  }
  const disconnect = async () => { await telegramUnlink(); setLink(''); await refresh() }

  return (
    <section className="account-card">
      <h2 className="account-card-title">✈️ {t('account.telegram')}</h2>
      {linked ? (
        <>
          <p>✓ {t('account.tgLinked')}</p>
          <button type="button" className="link-btn" onClick={disconnect}>{t('account.tgDisconnect')}</button>
        </>
      ) : unavailable ? (
        <p className="muted">{t('account.tgUnavailable')}</p>
      ) : (
        <>
          <p className="muted">{t('account.tgNotLinked')}</p>
          {link ? (
            <>
              <a className="btn-primary" href={link} target="_blank" rel="noopener noreferrer">{t('account.tgOpen')}</a>
              <p className="muted small">{t('account.tgWaiting')}</p>
            </>
          ) : (
            <button type="button" className="btn-primary" onClick={connect}>{t('account.tgConnect')}</button>
          )}
        </>
      )}
    </section>
  )
}

function DeleteAccount() {
  const { t } = useI18n()
  const { logout } = useAuth()
  const [confirming, setConfirming] = useState(false)

  const remove = async () => {
    await deleteMe()
    await logout()
    window.location.href = '/'
  }

  return (
    <section className="account-card danger-card">
      <h2 className="account-card-title">{t('account.deleteTitle')}</h2>
      <p className="muted">{t('account.deleteText')}</p>
      {confirming ? (
        <div className="row-gap">
          <button type="button" className="btn-danger" onClick={remove}>{t('account.deleteConfirm')}</button>
          <button type="button" className="btn-ghost" onClick={() => setConfirming(false)}>{t('account.cancel')}</button>
        </div>
      ) : (
        <button type="button" className="btn-ghost" onClick={() => setConfirming(true)}>{t('account.delete')}</button>
      )}
    </section>
  )
}

export default function AccountPage() {
  const { t } = useI18n()
  const ago = usePostedAgo()
  const { me, ready, openLogin, logout } = useAuth()
  const profile = me?.profile

  return (
    <>
      <Nav />
      <main className="page-wrap">
        <div className="section-label">{t('account.label')}</div>
        <h1 className="page-title">{t('account.title')}</h1>

        {!ready ? (
          <div className="empty-state"><div className="loading-spinner" style={{ margin: '0 auto' }} /></div>
        ) : !me ? (
          <div className="empty-state">
            <p>{t('account.loginNeeded')}</p>
            <button type="button" className="btn-primary" onClick={openLogin} style={{ marginTop: 16 }}>{t('nav.login')}</button>
          </div>
        ) : (
          <div className="account-grid">
            <div className="account-main">
              <section className="account-card">
                <h2 className="account-card-title">{t('account.profile')}</h2>
                <p className="muted small">{t('account.email')}: {me.user.email}</p>
                {profile ? (
                  <>
                    <dl className="account-facts">
                      <div><dt>{t('account.level')}</dt><dd>{profile.level ? t(`level.${profile.level}` as MessageKey) : '—'}</dd></div>
                      <div><dt>{t('account.roles')}</dt><dd>{profile.target_roles.length
                        ? profile.target_roles.map((r) => t(`cat.${r}` as MessageKey)).join(', ') : t('account.allRoles')}</dd></div>
                      <div><dt>{t('account.salary')}</dt><dd>{profile.preferred_salary ? `${formatTenge(profile.preferred_salary)} ₸` : '—'}</dd></div>
                    </dl>
                    <div className="profile-summary-title">{t('account.skills')}</div>
                    <div className="profile-tags">
                      {profile.skills.map((s) => <span className="profile-tag" key={s}>{s}</span>)}
                    </div>
                    <p className="muted small">{t('account.updated', { when: ago(profile.updated_at) })}</p>
                    <a className="btn-ghost" href="/#ai-agent">{t('account.updateProfile')}</a>
                  </>
                ) : (
                  <>
                    <p className="muted">{t('account.noProfile')}</p>
                    <a className="btn-primary" href="/#ai-agent">{t('nav.match')}</a>
                  </>
                )}
              </section>
              {profile && <TodaysMatches />}
            </div>
            <aside className="account-side">
              <TelegramCard />
              <button type="button" className="btn-ghost" onClick={async () => { await logout(); window.location.href = '/' }}>
                {t('nav.logout')}
              </button>
              <DeleteAccount />
            </aside>
          </div>
        )}
      </main>
      <Footer />
    </>
  )
}
