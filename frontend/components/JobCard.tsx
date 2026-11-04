'use client'
import { useState } from 'react'
import type { Job } from '@/lib/types'
import { formatTenge, usePostedAgo, useI18n, type MessageKey } from '@/lib/i18n'

const FORMAT_EMOJI: Record<string, string> = {
  remote: '🌍', hybrid: '🔀', office: '🏢',
}

export default function JobCard({ job }: { job: Job }) {
  const { t } = useI18n()
  const postedAgo = usePostedAgo()
  const [expanded, setExpanded] = useState(false)

  const cur = job.currency === 'KZT' ? '₸' : job.currency === 'USD' ? '$' : job.currency
  const salary = !job.salary_from && !job.salary_to
    ? t('job.salaryNotListed')
    : job.salary_from && job.salary_to && job.salary_from !== job.salary_to
      ? `${formatTenge(job.salary_from)} – ${formatTenge(job.salary_to)} ${cur}`
      : job.salary_from
        ? (job.salary_to ? `${formatTenge(job.salary_from)} ${cur}` : t('job.from', { v: `${formatTenge(job.salary_from)} ${cur}` }))
        : t('job.upTo', { v: `${formatTenge(job.salary_to!)} ${cur}` })
  const label = (prefix: 'cat' | 'level' | 'format', value: string) =>
    value ? t(`${prefix}.${value}` as MessageKey) : ''
  const posted = postedAgo(job.posted_at)

  return (
    <div
      className={`job-card${expanded ? ' expanded' : ''}`}
      onClick={() => setExpanded(!expanded)}
    >
      <div className="job-top">
        <div className="job-logo">{FORMAT_EMOJI[job.work_format] ?? '💼'}</div>
        <div className="job-badges">
          {job.work_format && <span className={`badge badge-${job.work_format}`}>{label('format', job.work_format)}</span>}
          {job.level && job.level !== 'unknown' && <span className={`badge badge-${job.level}`}>{label('level', job.level)}</span>}
        </div>
      </div>

      <div className="job-title">{job.title}</div>
      <div className="job-company">
        {[job.company, job.city, posted && t('job.posted', { when: posted })].filter(Boolean).join(' · ')}
      </div>

      {job.description && (
        <div className="job-description">{job.description}</div>
      )}

      <div className="job-skills">
        {job.skills.slice(0, 6).map((s) => (
          <span className="skill-tag" key={s}>{s}</span>
        ))}
        {job.skills.length > 6 && (
          <span className="skill-tag">+{job.skills.length - 6}</span>
        )}
      </div>

      {expanded && (
        <div className="job-full-details">
          {job.description && (
            <>
              <div className="job-section-title">{t('job.description')}</div>
              <div className="job-description-full" style={{ whiteSpace: 'pre-line' }}>{job.description}</div>
            </>
          )}

          <div className="job-section-title">{t('job.info')}</div>
          <ul className="job-list">
            <li>{t('job.category')}: {label('cat', job.category)}</li>
            {job.level && job.level !== 'unknown' && <li>{t('job.level')}: {label('level', job.level)}</li>}
            {job.work_format && <li>{t('job.format')}: {label('format', job.work_format)}</li>}
            {job.city && <li>{t('job.location')}: {job.city}</li>}
            <li>{t('job.source')}: {job.source}</li>
          </ul>

          {job.skills.length > 0 && (
            <>
              <div className="job-section-title">{t('job.skills', { n: job.skills.length })}</div>
              <div className="job-skills-full">
                {job.skills.map((s) => <span key={s} className="skill-tag-full">{s}</span>)}
              </div>
            </>
          )}
        </div>
      )}

      <div className="job-bottom">
        <div>
          <div className="job-salary">{salary}</div>
          <div className="job-meta">{label('cat', job.category)}</div>
        </div>
        {job.url && (
          <a className="job-expand-btn" href={job.url} target="_blank" rel="noopener noreferrer"
             onClick={(e) => e.stopPropagation()}>
            {t('job.open')}
          </a>
        )}
      </div>
    </div>
  )
}
