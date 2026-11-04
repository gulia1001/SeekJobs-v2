'use client'
import { useCallback, useEffect, useState } from 'react'
import Footer from '@/components/Footer'
import Nav from '@/components/Nav'
import { deleteApplication, listApplications, updateApplication } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { usePostedAgo, useI18n, type MessageKey } from '@/lib/i18n'
import type { Application, ApplicationStatus } from '@/lib/types'

const STATUSES: ApplicationStatus[] = ['saved', 'applied', 'interview', 'offer', 'rejected']

function ApplicationCard({ app, onChange, onRemove }: {
  app: Application
  onChange: (a: Application) => void
  onRemove: (id: number) => void
}) {
  const { t } = useI18n()
  const ago = usePostedAgo()
  const [notes, setNotes] = useState(app.notes ?? '')
  const [notesSaved, setNotesSaved] = useState(false)

  const setStatus = async (status: ApplicationStatus) => {
    onChange((await updateApplication(app.id, { status })).application)
  }
  const saveNotes = async () => {
    onChange((await updateApplication(app.id, { notes })).application)
    setNotesSaved(true)
  }

  return (
    <article className="board-card">
      <div className="board-card-title">{app.title}</div>
      <div className="board-card-meta">
        {[app.company, t('tracker.updated', { when: ago(app.updated_at) })].filter(Boolean).join(' · ')}
      </div>
      <label className="board-field">
        <select id={`status-${app.id}`} className="ai-input board-select" value={app.status} aria-label={app.title}
                onChange={(e) => setStatus(e.target.value as ApplicationStatus)}>
          {STATUSES.map((s) => <option key={s} value={s}>{t(`tracker.status.${s}` as MessageKey)}</option>)}
        </select>
      </label>
      <details className="board-notes" open={Boolean(app.notes)}>
        <summary>{t('tracker.notes')}</summary>
        <textarea id={`notes-${app.id}`} className="ai-input" rows={3} placeholder={t('tracker.notesPh')}
                  value={notes} onChange={(e) => { setNotes(e.target.value); setNotesSaved(false) }} />
        <button type="button" className="btn-mini btn-mini-ghost" onClick={saveNotes} disabled={notes === (app.notes ?? '')}>
          {notesSaved && notes === (app.notes ?? '') ? `✓ ${t('tracker.notesSaved')}` : t('tracker.saveNotes')}
        </button>
      </details>
      <div className="board-card-actions">
        {app.url && <a className="btn-mini btn-mini-ghost" href={app.url} target="_blank" rel="noopener noreferrer">{t('tracker.open')}</a>}
        <button type="button" className="link-btn danger" onClick={() => onRemove(app.id)}>{t('tracker.remove')}</button>
      </div>
    </article>
  )
}

export default function TrackerPage() {
  const { t } = useI18n()
  const { user, ready, openLogin } = useAuth()
  const [apps, setApps] = useState<Application[] | null>(null)

  const load = useCallback(() => {
    listApplications().then(({ applications }) => setApps(applications)).catch(() => setApps([]))
  }, [])
  useEffect(() => { if (user) load() }, [user, load])

  const replace = (a: Application) => setApps((prev) => prev?.map((x) => (x.id === a.id ? a : x)) ?? null)
  const remove = async (id: number) => {
    await deleteApplication(id)
    setApps((prev) => prev?.filter((x) => x.id !== id) ?? null)
  }

  return (
    <>
      <Nav />
      <main className="page-wrap">
        <div className="section-label">{t('tracker.label')}</div>
        <h1 className="page-title">{t('tracker.title')}</h1>
        <p className="page-sub">{t('tracker.sub')}</p>

        {!ready || (user && apps === null) ? (
          <div className="empty-state"><div className="loading-spinner" style={{ margin: '0 auto' }} /></div>
        ) : !user ? (
          <div className="empty-state">
            <p>{t('tracker.loginNeeded')}</p>
            <button type="button" className="btn-primary" onClick={openLogin} style={{ marginTop: 16 }}>{t('nav.login')}</button>
          </div>
        ) : apps!.length === 0 ? (
          <div className="empty-state">
            <p>{t('tracker.empty')}</p>
            <a className="btn-primary" href="/#ai-agent" style={{ marginTop: 16, display: 'inline-block' }}>{t('tracker.findMatches')}</a>
          </div>
        ) : (
          <div className="board">
            {STATUSES.map((status) => {
              const items = apps!.filter((a) => a.status === status)
              return (
                <section className={`board-col board-col--${status}`} key={status} aria-label={t(`tracker.status.${status}` as MessageKey)}>
                  <h2 className="board-col-title">
                    {t(`tracker.status.${status}` as MessageKey)} <span className="board-count">{items.length}</span>
                  </h2>
                  {items.map((a) => <ApplicationCard key={a.id} app={a} onChange={replace} onRemove={remove} />)}
                </section>
              )
            })}
          </div>
        )}
      </main>
      <Footer />
    </>
  )
}
