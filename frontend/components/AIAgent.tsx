'use client'
import { useEffect, useRef, useState } from 'react'
import type { AnalysisResult, GeneratedCV, Match } from '@/lib/types'
import { analyzeProfile, generateCV } from '@/lib/api'
import RoleSelector from './RoleSelector'
import CVModal from './CVModal'

const LOADING_MESSAGES = [
  'Parsing your CV...',
  'Analyzing GitHub repositories...',
  'Scanning LinkedIn profile...',
  'Matching against KZ IT vacancies...',
  'Scoring skill overlap per role...',
  'Comparing salary expectations...',
  'Generating your top matches...',
]

const ROLE_LABELS: Record<string, string> = {
  software_engineering: 'Software Engineering',
  devops: 'DevOps',
  analytics: 'Analytics',
  data: 'Data / ML',
  qa: 'QA',
  security: 'Security',
  design: 'Design',
  product: 'Product',
  management: 'Management',
}

function formatSalaryKZT(amount?: number, currency = 'KZT'): string {
  if (!amount) return '—'
  const sym = currency === 'KZT' ? '₸' : currency === 'USD' ? '$' : currency
  return `${sym}${Math.round(amount / 1000)}K`
}

function SalaryStatus({ status }: { status: Match['salary_comparison']['status'] }) {
  if (status === 'unknown') return null
  const labels = { below: '↓ Below market', at: '≈ At market', above: '↑ Above market' }
  return <span className={`salary-status salary-status--${status}`}>{labels[status]}</span>
}

interface CVModalState {
  jobId: string
  jobTitle: string
  company: string
  jobSkills: string[]
  cv: GeneratedCV | null
}

export default function AIAgent() {
  const sectionRef = useRef<HTMLDivElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [linkedinUrl, setLinkedinUrl] = useState('')
  const [githubUrl, setGithubUrl] = useState('')
  const [preferredSalary, setPreferredSalary] = useState('')
  const [roles, setRoles] = useState<string[]>([])
  const [phase, setPhase] = useState<'idle' | 'loading' | 'results'>('idle')
  const [loadingMsg, setLoadingMsg] = useState(LOADING_MESSAGES[0])
  const [results, setResults] = useState<AnalysisResult | null>(null)
  const [error, setError] = useState('')
  const [modalState, setModalState] = useState<CVModalState | null>(null)

  useEffect(() => {
    const el = sectionRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { el.classList.add('visible'); observer.disconnect() } },
      { threshold: 0.05 }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (phase !== 'loading') return
    let i = 0
    const interval = setInterval(() => {
      i = (i + 1) % LOADING_MESSAGES.length
      setLoadingMsg(LOADING_MESSAGES[i])
    }, 1200)
    return () => clearInterval(interval)
  }, [phase])

  const handleFileChange = (f: File) => {
    setFile(f)
  }

  const runAnalysis = async () => {
    if (!file && !linkedinUrl && !githubUrl) {
      setError('Please upload a CV or provide a LinkedIn or GitHub URL.')
      return
    }
    setError('')
    setPhase('loading')
    setLoadingMsg(LOADING_MESSAGES[0])

    const formData = new FormData()
    if (file) formData.append('cv_file', file)
    if (linkedinUrl) formData.append('linkedin_url', linkedinUrl)
    if (githubUrl) formData.append('github_url', githubUrl)
    if (preferredSalary) formData.append('preferred_salary', preferredSalary)
    roles.forEach((r) => formData.append('target_roles', r))

    try {
      const data = await analyzeProfile(formData)
      setResults(data)
      setPhase('results')
    } catch (e: unknown) {
      console.error('Analysis failed:', e)
      setError(e instanceof Error ? e.message : 'Analysis failed')
      setPhase('idle')
    }
  }

  const openCVModal = async (match: Match) => {
    const state: CVModalState = {
      jobId: match.job.id,
      jobTitle: match.job.title,
      company: match.job.company,
      jobSkills: match.job.skills,
      cv: null,
    }
    setModalState(state)

    try {
      const cv = await generateCV({
        job_id: match.job.id,
        job_title: match.job.title,
        job_skills: match.job.skills,
        user_profile: results?.profile ?? {},
        cv_text: results?.profile?.cv_text ?? '',
      })
      setModalState((prev) => prev ? { ...prev, cv } : prev)
    } catch {
      setModalState((prev) => prev ? {
        ...prev, cv: {
          name: 'Your Name', role: match.job.title,
          summary: 'Could not generate CV — please try again.',
          experience: [], education: [], skills: results?.profile?.skills ?? [],
          latex: '', tailored_note: '',
        }
      } : prev)
    }
  }

  const roleKeys = results ? Object.keys(results.by_role) : []

  return (
    <>
      <div id="ai-agent" className="ai-section">
        <div className="ai-hero-text reveal" ref={sectionRef}>
          <div className="section-label" style={{ justifyContent: 'center' }}>AI Agent</div>
          <h2>Your personal<br /><em>career intelligence layer</em></h2>
          <p>Upload your profile once. Get tailored matches and custom CVs — ready to send.</p>
        </div>

        <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 48px' }}>
          <div className="ai-container">
            {/* LEFT — INPUT */}
            <div className="ai-left">
              <div className="ai-step-label"><span>Step 1</span> Your Profile</div>

              {/* CV UPLOAD */}
              <div
                className={`upload-zone${dragOver ? ' drag-over' : ''}`}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault(); setDragOver(false)
                  const f = e.dataTransfer.files[0]
                  if (f) handleFileChange(f)
                }}
              >
                <input
                  type="file"
                  accept=".pdf,.doc,.docx"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFileChange(f) }}
                />
                <div className="upload-icon">{file ? '✅' : '📄'}</div>
                <div className="upload-title" style={{ color: file ? 'var(--accent3)' : undefined }}>
                  {file ? file.name : 'Drop your CV here'}
                </div>
                <div className="upload-sub">PDF or Word · up to 5MB</div>
              </div>

              <div className="or-divider">or paste links</div>

              <div className="input-group">
                <div className="input-label">🔗 LinkedIn URL</div>
                <input
                  className="ai-input"
                  type="url"
                  placeholder="https://linkedin.com/in/yourname"
                  value={linkedinUrl}
                  onChange={(e) => setLinkedinUrl(e.target.value)}
                />
              </div>

              <div className="input-group">
                <div className="input-label">💻 GitHub URL</div>
                <input
                  className="ai-input"
                  type="url"
                  placeholder="https://github.com/yourusername"
                  value={githubUrl}
                  onChange={(e) => setGithubUrl(e.target.value)}
                />
              </div>

              <div className="input-group">
                <div className="input-label">💰 Preferred Salary (₸/month)</div>
                <input
                  className="ai-input"
                  type="number"
                  placeholder="e.g. 400000"
                  value={preferredSalary}
                  onChange={(e) => setPreferredSalary(e.target.value)}
                />
              </div>

              <div className="input-group">
                <div className="input-label">🎯 Target Roles (pick 1 or more)</div>
                <RoleSelector selected={roles} onChange={setRoles} />
              </div>

              {error && (
                <div style={{ color: 'var(--accent)', fontSize: 12, marginTop: 8, marginBottom: 4 }}>
                  ⚠ {error}
                </div>
              )}

              <button
                type="button"
                className="analyze-btn"
                onClick={runAnalysis}
                disabled={phase === 'loading'}
              >
                <span>⚡</span>
                {phase === 'loading' ? 'Analyzing...' : 'Analyze & Match Me'}
              </button>
            </div>

            {/* RIGHT — OUTPUT */}
            <div className="ai-right">
              {phase === 'idle' && (
                <div className="ai-output-placeholder">
                  <div className="big-icon">🤖</div>
                  <p>Fill in your profile on the left and hit <strong style={{ color: 'var(--text)' }}>Analyze</strong> to see your top job matches.</p>
                </div>
              )}

              {phase === 'loading' && (
                <div className="ai-loading">
                  <div className="loading-spinner" />
                  <div className="loading-text">{loadingMsg}</div>
                </div>
              )}

              {phase === 'results' && results && (
                <div key="results-view">
                  <div className="ai-step-label"><span>Step 2</span> Your Matches</div>

                  {/* PROFILE SUMMARY */}
                  {results.profile.skills.length > 0 && (
                    <div className="profile-summary">
                      <div className="profile-summary-title">
                        {results.profile.name ? `${results.profile.name} · ` : ''}Detected Skills
                      </div>
                      <div className="profile-tags">
                        {results.profile.skills.slice(0, 20).map((s) => (
                          <span className="profile-tag" key={s}>{s}</span>
                        ))}
                      </div>

                      {/* PROJECTS */}
                      {results.profile.top_repos?.length > 0 && (
                        <div style={{ marginTop: 16 }}>
                          <div className="profile-summary-title">Top GitHub Projects</div>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 8 }}>
                            {results.profile.top_repos.slice(0, 3).map((repo: any) => (
                              <div key={repo.name} style={{ fontSize: 11, background: 'rgba(255,255,255,0.03)', padding: '8px', borderRadius: '4px', border: '1px solid rgba(255,255,255,0.05)' }}>
                                <strong style={{ color: 'var(--accent3)' }}>{repo.name}</strong> · {repo.description}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* CERTIFICATIONS */}
                      {results.profile.certifications?.length > 0 && (
                        <div style={{ marginTop: 16 }}>
                          <div className="profile-summary-title">LinkedIn Certifications</div>
                          <div className="profile-tags">
                            {results.profile.certifications.slice(0, 5).map((cert: any) => (
                              <span className="profile-tag" key={cert.name} style={{ background: 'rgba(52, 211, 153, 0.1)', color: '#34d399', borderColor: 'rgba(52, 211, 153, 0.2)' }}>
                                📜 {cert.name}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* PER-ROLE SECTIONS */}
                  {roleKeys.length === 0 && (
                    <div className="empty-state">
                      <p>No matches found. Try selecting different roles or adding more profile info.</p>
                    </div>
                  )}

                  {roleKeys.map((role) => {
                    const roleData = results.by_role[role]
                    const expected = preferredSalary ? Number(preferredSalary) : undefined
                    const marketAvg = roleData.market_avg_salary
                    const salaryStatus: Match['salary_comparison']['status'] =
                      !expected || !marketAvg ? 'unknown'
                        : expected < marketAvg * 0.9 ? 'below'
                          : expected > marketAvg * 1.1 ? 'above'
                            : 'at'

                    // Show only top 10 matches per role
                    const topMatches = roleData.matches.slice(0, 10)

                    return (
                      <div className="match-role-section" key={role}>
                        <div className="match-role-header">
                          <div className="match-role-title">
                            {ROLE_LABELS[role] ?? role} · {topMatches.length} of {roleData.matches.length} top matches
                          </div>
                          {marketAvg > 0 && (
                            <div className="match-salary-info">
                              Market avg: {formatSalaryKZT(marketAvg, roleData.currency)}
                              {expected && <>&nbsp;<SalaryStatus status={salaryStatus} /></>}
                            </div>
                          )}
                        </div>

                        {topMatches.map((match) => (
                          <div className="match-card" key={match.job.id}>
                            <div className="match-rank">#{match.rank}</div>

                            <div className="match-top">
                              <span className="match-score">{match.score}% match</span>
                              <div className="match-title">{match.job.title}</div>
                            </div>

                            <div className="match-company">
                              {match.job.company} · {match.job.city} ·{' '}
                              {formatSalaryKZT(match.job.salary_avg ?? match.job.salary_from, match.job.currency)}
                            </div>

                            <div className="match-reason">{match.reason}</div>

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
                              <button
                                className="btn-mini btn-mini-primary"
                                onClick={() => openCVModal(match)}
                              >
                                Generate CV →
                              </button>
                              <button className="btn-mini btn-mini-ghost">
                                {match.job.work_format} · {match.job.level}
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* CV MODAL */}
      {modalState && (
        <CVModal
          cv={modalState.cv}
          jobTitle={modalState.jobTitle}
          company={modalState.company}
          onClose={() => setModalState(null)}
        />
      )}
    </>
  )
}
