'use client'
import { useEffect, useRef, useState } from 'react'
import type { Job } from '@/lib/types'
import { fetchJobs } from '@/lib/api'
import { useI18n, type MessageKey } from '@/lib/i18n'
import JobCard from './JobCard'

const CATEGORIES = ['all', 'software_engineering', 'devops', 'analytics', 'data', 'qa', 'security', 'design', 'product', 'management']
const LEVELS = ['all', 'intern', 'junior', 'middle', 'senior', 'lead']

export default function Vacancies() {
  const { t } = useI18n()
  const ref = useRef<HTMLElement>(null)
  const [jobs, setJobs] = useState<Job[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(1)
  const [category, setCategory] = useState('all')
  const [level, setLevel] = useState('all')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { el.classList.add('visible'); observer.disconnect() } },
      { threshold: 0.05 }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    setLoading(true)
    fetchJobs({ page, limit: 12, category, level })
      .then((data) => {
        setJobs(data.jobs)
        setTotal(data.total)
        setPages(data.pages)
      })
      .catch(() => setJobs([]))
      .finally(() => setLoading(false))
  }, [page, category, level])

  const handleCategory = (val: string) => {
    setCategory(val)
    setPage(1)
  }

  const handleLevel = (val: string) => {
    setLevel(val)
    setPage(1)
  }

  return (
    <section id="jobs" className="vacancies-section reveal" ref={ref}>
      <div className="vacancies-header">
        <div>
          <div className="section-label">{t('vac.label')}</div>
          <h2>{t('vac.title1')} <em>{t('vac.title2')}</em></h2>
          {total > 0 && <p style={{ color: 'var(--muted)', fontSize: 12, marginTop: 4 }}>{t('vac.found', { n: total })}</p>}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-end' }}>
          <div className="filter-tabs">
            {CATEGORIES.map((c) => (
              <button
                key={c}
                className={`filter-tab${category === c ? ' active' : ''}`}
                onClick={() => handleCategory(c)}
              >
                {t(`cat.${c}` as MessageKey)}
              </button>
            ))}
          </div>
          <div className="filter-tabs">
            {LEVELS.map((l) => (
              <button
                key={l}
                className={`filter-tab${level === l ? ' active' : ''}`}
                onClick={() => handleLevel(l)}
              >
                {t(`level.${l}` as MessageKey)}
              </button>
            ))}
          </div>
        </div>
      </div>

      {loading ? (
        <div className="empty-state">
          <div className="loading-spinner" style={{ margin: '0 auto' }} />
          <p>{t('vac.loading')}</p>
        </div>
      ) : jobs.length === 0 ? (
        <div className="empty-state">
          <p style={{ fontSize: 32, opacity: 0.3 }}>🔍</p>
          <p>{t('vac.empty')}</p>
        </div>
      ) : (
        <>
          <div className="jobs-grid">
            {jobs.map((job) => <JobCard key={job.id} job={job} />)}
          </div>

          {pages > 1 && (
            <div className="pagination">
              <button
                className="page-btn"
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
              >
                {t('vac.prev')}
              </button>
              {Array.from({ length: Math.min(pages, 7) }, (_, i) => {
                const p = i + 1
                return (
                  <button
                    key={p}
                    className={`page-btn${page === p ? ' active' : ''}`}
                    onClick={() => setPage(p)}
                  >
                    {p}
                  </button>
                )
              })}
              {pages > 7 && <span style={{ color: 'var(--muted)', padding: '0 4px' }}>…</span>}
              <button
                className="page-btn"
                disabled={page === pages}
                onClick={() => setPage((p) => p + 1)}
              >
                {t('vac.next')}
              </button>
            </div>
          )}
        </>
      )}
    </section>
  )
}
