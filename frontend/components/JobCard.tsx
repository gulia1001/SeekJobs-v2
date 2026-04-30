'use client'
import { useState } from 'react'
import type { Job } from '@/lib/types'

function formatSalary(job: Job): string {
  if (!job.salary_from && !job.salary_to) return 'Salary not listed'
  const cur = job.currency === 'KZT' ? '₸' : job.currency === 'USD' ? '$' : job.currency
  const fmt = (n: number) => n >= 1000 ? `${Math.round(n / 1000)}K` : String(n)
  if (job.salary_from && job.salary_to) return `${cur}${fmt(job.salary_from)} – ${fmt(job.salary_to)}`
  if (job.salary_from) return `from ${cur}${fmt(job.salary_from)}`
  return `up to ${cur}${fmt(job.salary_to!)}`
}

const FORMAT_EMOJI: Record<string, string> = {
  remote: '🌍', hybrid: '🔀', office: '🏢',
}

export default function JobCard({ job }: { job: Job }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div 
      className={`job-card${expanded ? ' expanded' : ''}`}
      onClick={() => setExpanded(!expanded)}
    >
      <div className="job-top">
        <div className="job-logo">{FORMAT_EMOJI[job.work_format] ?? '💼'}</div>
        <div className="job-badges">
          <span className={`badge badge-${job.work_format}`}>{job.work_format}</span>
          <span className={`badge badge-${job.level}`}>{job.level}</span>
        </div>
      </div>

      <div className="job-title">{job.title}</div>
      <div className="job-company">{job.company} · {job.city}</div>

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
              <div className="job-section-title">Job Description</div>
              <div className="job-description-full" style={{ whiteSpace: 'pre-line' }}>{job.description}</div>
            </>
          )}
          
          <div className="job-section-title">Salary Details</div>
          <ul className="job-list">
            <li>Amount: {formatSalary(job)}</li>
            <li>Currency: {job.currency}</li>
          </ul>

          <div className="job-section-title">Job Info</div>
          <ul className="job-list">
            <li>Category: {job.category}</li>
            <li>Level: {job.level}</li>
            <li>Format: {job.work_format}</li>
            <li>Location: {job.city}</li>
            <li>Source: {job.source}</li>
          </ul>
          
          {job.skills.length > 0 && (
            <>
              <div className="job-section-title">Required Skills ({job.skills.length})</div>
              <div className="job-skills-full">
                {job.skills.map((s) => <span key={s} className="skill-tag-full">{s}</span>)}
              </div>
            </>
          )}
        </div>
      )}

      <div className="job-bottom">
        <div>
          <div className="job-salary">{formatSalary(job)}</div>
          <div className="job-meta">{job.category}</div>
        </div>
        <button
          className="job-expand-btn"
          onClick={(e) => {
            e.stopPropagation()
            if (job.url) window.open(job.url, '_blank')
          }}
        >
          View Details →
        </button>
      </div>
    </div>
  )
}
