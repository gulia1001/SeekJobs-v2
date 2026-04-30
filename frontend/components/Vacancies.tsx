'use client'
import { useEffect, useRef, useState } from 'react'
import type { Job } from '@/lib/types'
import { fetchJobs } from '@/lib/api'
import JobCard from './JobCard'

const CATEGORIES = [
  { label: 'All', value: 'all' },
  { label: 'Software Eng', value: 'software_engineering' },
  { label: 'DevOps', value: 'devops' },
  { label: 'Analytics', value: 'analytics' },
  { label: 'Data / ML', value: 'data' },
  { label: 'QA', value: 'qa' },
  { label: 'Security', value: 'security' },
  { label: 'Design', value: 'design' },
]

const LEVELS = [
  { label: 'All Levels', value: 'all' },
  { label: 'Junior', value: 'junior' },
  { label: 'Middle', value: 'middle' },
  { label: 'Senior', value: 'senior' },
]

export default function Vacancies() {
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
          <div className="section-label">Open Positions</div>
          <h2>Live <em>Vacancies</em></h2>
          {total > 0 && <p style={{ color: 'var(--muted)', fontSize: 12, marginTop: 4 }}>{total.toLocaleString()} jobs found</p>}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-end' }}>
          <div className="filter-tabs">
            {CATEGORIES.map((c) => (
              <button
                key={c.value}
                className={`filter-tab${category === c.value ? ' active' : ''}`}
                onClick={() => handleCategory(c.value)}
              >
                {c.label}
              </button>
            ))}
          </div>
          <div className="filter-tabs">
            {LEVELS.map((l) => (
              <button
                key={l.value}
                className={`filter-tab${level === l.value ? ' active' : ''}`}
                onClick={() => handleLevel(l.value)}
              >
                {l.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {loading ? (
        <div className="empty-state">
          <div className="loading-spinner" style={{ margin: '0 auto' }} />
          <p>Loading vacancies...</p>
        </div>
      ) : jobs.length === 0 ? (
        <div className="empty-state">
          <p style={{ fontSize: 32, opacity: 0.3 }}>🔍</p>
          <p>No vacancies found. Run the Airflow pipeline to populate job data.</p>
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
                ← Prev
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
                Next →
              </button>
            </div>
          )}
        </>
      )}
    </section>
  )
}
