'use client'
import { useState } from 'react'
import { usePostedAgo, useI18n, type MessageKey } from '@/lib/i18n'
import type { Match } from '@/lib/types'

export function shortSalary(amount?: number | null, currency = 'KZT'): string {
  if (!amount) return ''
  const sym = currency === 'KZT' ? '₸' : currency === 'USD' ? '$' : currency
  return `${Math.round(amount / 1000)}k ${sym}`
}

interface Props {
  match: Match
  saved: boolean
  onSave: (jobId: string) => Promise<void>
  onGenerateCv?: (match: Match) => void
}

export default function MatchCard({ match, saved, onSave, onGenerateCv }: Props) {
  const { t } = useI18n()
  const postedAgo = usePostedAgo()
  const [saving, setSaving] = useState(false)
  const { job } = match
  const posted = postedAgo(job.posted_at)
  // the backend's default explanation is English; show ours in the user's language instead
  const reason = match.reason && !match.reason.startsWith('You have ')
    ? match.reason
    : t('ai.reason', { have: match.skills_matched.length, need: match.skills_required })

  const save = async () => {
    setSaving(true)
    try { await onSave(job.id) } finally { setSaving(false) }
  }

  return (
    <div className="match-card">
      <div className="match-rank">#{match.rank}</div>

      <div className="match-top">
        <span className="match-score" title={t('ai.reason', { have: match.skills_matched.length, need: match.skills_required })}>
          {t('ai.match', { n: match.score })}
        </span>
        <div className="match-title">{job.title}</div>
      </div>

      <div className="match-company">
        {[job.company, job.city, shortSalary(job.salary_avg ?? job.salary_from, job.currency),
          posted && t('job.posted', { when: posted })].filter(Boolean).join(' · ')}
      </div>

      <div className="match-reason">{reason}</div>

      {(match.skills_matched.length > 0 || match.skills_missing.length > 0) && (
        <div className="skill-gap">
          {match.skills_matched.slice(0, 5).map((s) => (
            <span className="skill-gap-tag skill-match" key={s}>✓ {s}</span>
          ))}
          {match.skills_missing.slice(0, 4).map((s) => (
            <span className="skill-gap-tag skill-missing" key={s}>+ {s}</span>
          ))}
        </div>
      )}

      <div className="match-actions">
        {onGenerateCv && (
          <button className="btn-mini btn-mini-primary" onClick={() => onGenerateCv(match)}>
            {t('ai.generateCv')}
          </button>
        )}
        <button className={`btn-mini btn-mini-ghost${saved ? ' is-saved' : ''}`} onClick={save}
                disabled={saved || saving} aria-pressed={saved}>
          {saved ? t('ai.saved') : t('ai.save')}
        </button>
        {job.url && (
          <a className="btn-mini btn-mini-ghost" href={job.url} target="_blank" rel="noopener noreferrer">
            {t('ai.viewJob')}
          </a>
        )}
        {(job.work_format || (job.level && job.level !== 'unknown')) && (
          <span className="match-meta">
            {[job.work_format && t(`format.${job.work_format}` as MessageKey),
              job.level && job.level !== 'unknown' && t(`level.${job.level}` as MessageKey)].filter(Boolean).join(' · ')}
          </span>
        )}
      </div>
    </div>
  )
}
