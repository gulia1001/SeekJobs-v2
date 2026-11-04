'use client'
import { useEffect, useRef, useState } from 'react'
import type { AnalysisResult, GeneratedCV, Match } from '@/lib/types'
import { ApiError, analyzeProfile, generateCV, saveProfile } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { formatTenge, useI18n, type MessageKey } from '@/lib/i18n'
import { useSavedJobs } from '@/lib/useSavedJobs'
import RoleSelector from './RoleSelector'
import CVModal from './CVModal'
import MatchCard from './MatchCard'

const LOADING_KEYS: MessageKey[] = ['ai.loading1', 'ai.loading2', 'ai.loading3', 'ai.loading4', 'ai.loading5', 'ai.loading6']
const MAX_CV_BYTES = 5 * 1024 * 1024
const CV_EXTENSIONS = ['pdf', 'docx', 'txt']

interface CVModalState {
  jobTitle: string
  company: string
  cv: GeneratedCV | null
}

export default function AIAgent() {
  const { t } = useI18n()
  const { user, openLogin } = useAuth()
  const { savedIds, save } = useSavedJobs()
  const sectionRef = useRef<HTMLDivElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [linkedinFile, setLinkedinFile] = useState<File | null>(null)
  const [githubUrl, setGithubUrl] = useState('')
  const [preferredSalary, setPreferredSalary] = useState('')
  const [roles, setRoles] = useState<string[]>([])
  const [phase, setPhase] = useState<'idle' | 'loading' | 'results'>('idle')
  const [loadingIdx, setLoadingIdx] = useState(0)
  const [results, setResults] = useState<AnalysisResult | null>(null)
  const [error, setError] = useState('')
  const [profileSaved, setProfileSaved] = useState(false)
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
    const interval = setInterval(() => setLoadingIdx((i) => (i + 1) % LOADING_KEYS.length), 1200)
    return () => clearInterval(interval)
  }, [phase])

  const handleFileChange = (f: File) => {
    const ext = f.name.split('.').pop()?.toLowerCase() ?? ''
    if (!CV_EXTENSIONS.includes(ext)) { setError(t('ai.err.fileType')); return }
    if (f.size > MAX_CV_BYTES) { setError(t('ai.err.size')); return }
    setError('')
    setFile(f)
  }

  const salaryNumber = () => {
    const digits = preferredSalary.replace(/\D/g, '')
    return digits ? Number(digits) : null
  }

  const runAnalysis = async () => {
    if (!file && !linkedinFile && !githubUrl) { setError(t('ai.err.empty')); return }
    setError('')
    setProfileSaved(false)
    setPhase('loading')
    setLoadingIdx(0)

    const formData = new FormData()
    if (file) formData.append('cv_file', file)
    if (linkedinFile) formData.append('linkedin_pdf', linkedinFile)
    if (githubUrl) formData.append('github_url', githubUrl)
    if (preferredSalary) formData.append('preferred_salary', preferredSalary)
    roles.forEach((r) => formData.append('target_roles', r))

    try {
      setResults(await analyzeProfile(formData))
      setPhase('results')
    } catch (e: unknown) {
      if (e instanceof ApiError && e.status === 0) setError(t('ai.err.network'))
      else if (e instanceof ApiError && e.status === 422 && e.message.startsWith('Could not extract')) setError(t('ai.err.noSkills'))
      else if (e instanceof ApiError && e.status === 415) setError(t('ai.err.fileType'))
      else if (e instanceof ApiError && e.status === 413) setError(t('ai.err.size'))
      else setError(e instanceof Error ? e.message : String(e))
      setPhase('idle')
    }
  }

  const storeProfile = async () => {
    if (!results) return
    if (!user) { openLogin(); return }
    try {
      await saveProfile({
        skills: results.profile.skills,
        level: results.profile.level ?? '',
        target_roles: roles,
        preferred_salary: salaryNumber(),
        cv_text: results.profile.cv_text ?? '',
        github_url: results.profile.github_url ?? '',
        linkedin_url: results.profile.linkedin_url ?? '',
      })
      setProfileSaved(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const openCVModal = async (match: Match) => {
    setModalState({ jobTitle: match.job.title, company: match.job.company, cv: null })
    try {
      const cv = await generateCV({
        job_id: match.job.id,
        job_title: match.job.title,
        job_skills: match.job.skills,
        user_profile: results?.profile ?? {},
        cv_text: results?.profile?.cv_text ?? '',
      })
      setModalState((prev) => (prev ? { ...prev, cv } : prev))
    } catch {
      setModalState((prev) => (prev ? {
        ...prev, cv: {
          name: '', role: match.job.title, summary: t('cv.failed'),
          experience: [], education: [], skills: results?.profile?.skills ?? [], latex: '', tailored_note: '',
        },
      } : prev))
    }
  }

  const roleKeys = results ? Object.keys(results.by_role) : []
  const expected = salaryNumber()

  return (
    <>
      <div id="ai-agent" className="ai-section">
        <div className="ai-hero-text reveal" ref={sectionRef}>
          <div className="section-label" style={{ justifyContent: 'center' }}>{t('ai.label')}</div>
          <h2>{t('ai.title1')}<br /><em>{t('ai.title2')}</em></h2>
          <p>{t('ai.sub')}</p>
        </div>

        <div className="ai-wrap">
          <div className="ai-container">
            {/* LEFT — INPUT */}
            <div className="ai-left">
              <div className="ai-step-label"><span>{t('ai.step1')}</span> {t('ai.profile')}</div>

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
                <input id="cv-file" type="file" accept=".pdf,.docx,.txt"
                       onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFileChange(f) }} />
                <div className="upload-icon">{file ? '✅' : '📄'}</div>
                <div className="upload-title" style={{ color: file ? 'var(--accent3)' : undefined }}>
                  {file ? file.name : t('ai.drop')}
                </div>
                <div className="upload-sub">{t('ai.dropHint')}</div>
              </div>

              <div className="or-divider">{t('ai.andOr')}</div>

              <div className="input-group">
                <label className="input-label" htmlFor="linkedin-pdf">🔗 {t('ai.linkedin')}</label>
                <input
                  id="linkedin-pdf"
                  className="ai-input"
                  type="file"
                  accept=".pdf"
                  onChange={(e) => {
                    const f = e.target.files?.[0]
                    if (!f) return
                    if (!f.name.toLowerCase().endsWith('.pdf')) { setError(t('ai.err.linkedinPdf')); return }
                    if (f.size > MAX_CV_BYTES) { setError(t('ai.err.size')); return }
                    setError('')
                    setLinkedinFile(f)
                  }}
                />
                <div className="upload-sub" style={{ marginTop: 4 }}>{t('ai.linkedinHint')}</div>
              </div>

              <div className="input-group">
                <label className="input-label" htmlFor="github-url">💻 {t('ai.github')}</label>
                <input id="github-url" className="ai-input" type="url" placeholder="https://github.com/…"
                       value={githubUrl} onChange={(e) => setGithubUrl(e.target.value)} />
              </div>

              <div className="input-group">
                <label className="input-label" htmlFor="salary">💰 {t('ai.salary')}</label>
                <input id="salary" className="ai-input" type="text" inputMode="numeric" placeholder={t('ai.salaryPh')}
                       value={preferredSalary} onChange={(e) => setPreferredSalary(e.target.value)} />
              </div>

              <div className="input-group">
                <div className="input-label">🎯 {t('ai.roles')}</div>
                <RoleSelector selected={roles} onChange={setRoles} />
              </div>

              {error && <div className="form-error" role="alert">⚠ {error}</div>}

              <button type="button" className="analyze-btn" onClick={runAnalysis} disabled={phase === 'loading'}>
                <span>⚡</span>
                {phase === 'loading' ? t('ai.analyzing') : t('ai.analyze')}
              </button>
            </div>

            {/* RIGHT — OUTPUT */}
            <div className="ai-right">
              {phase === 'idle' && (
                <div className="ai-output-placeholder">
                  <div className="big-icon">🎯</div>
                  <p>{t('ai.placeholder')}</p>
                </div>
              )}

              {phase === 'loading' && (
                <div className="ai-loading">
                  <div className="loading-spinner" />
                  <div className="loading-text">{t(LOADING_KEYS[loadingIdx])}</div>
                </div>
              )}

              {phase === 'results' && results && (
                <div key="results-view">
                  <div className="ai-step-label"><span>{t('ai.step2')}</span> {t('ai.matches')}</div>

                  {results.profile.skills.length > 0 && (
                    <div className="profile-summary">
                      <div className="profile-summary-title">
                        {results.profile.name ? `${results.profile.name} · ` : ''}{t('ai.detected')}
                      </div>
                      <div className="profile-tags">
                        {results.profile.skills.slice(0, 20).map((s) => (
                          <span className="profile-tag" key={s}>{s}</span>
                        ))}
                      </div>

                      {results.profile.top_repos?.length > 0 && (
                        <div style={{ marginTop: 16 }}>
                          <div className="profile-summary-title">{t('ai.projects')}</div>
                          <div className="repo-list">
                            {results.profile.top_repos.slice(0, 3).map((repo) => (
                              <div className="repo-item" key={repo.name}>
                                <strong>{repo.name}</strong> · {repo.description}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {results.profile.certifications?.length > 0 && (
                        <div style={{ marginTop: 16 }}>
                          <div className="profile-summary-title">{t('ai.certs')}</div>
                          <div className="profile-tags">
                            {results.profile.certifications.slice(0, 5).map((cert) => (
                              <span className="profile-tag cert-tag" key={cert.name}>📜 {cert.name}</span>
                            ))}
                          </div>
                        </div>
                      )}

                      <div className="save-profile">
                        {profileSaved ? (
                          <p className="save-profile-done">✓ {t('ai.profileSaved')} <a href="/account">{t('nav.account')} →</a></p>
                        ) : (
                          <>
                            <button type="button" className="btn-mini btn-mini-primary" onClick={storeProfile}>
                              {t('ai.saveProfile')}
                            </button>
                            {!user && <span className="save-profile-hint">{t('ai.loginToSave')}</span>}
                          </>
                        )}
                      </div>
                    </div>
                  )}

                  {roleKeys.length === 0 && (
                    <div className="empty-state"><p>{t('ai.noMatches')}</p></div>
                  )}

                  {roleKeys.map((role) => {
                    const roleData = results.by_role[role]
                    const marketAvg = roleData.market_avg_salary
                    const status = !expected || !marketAvg ? null
                      : expected < marketAvg * 0.9 ? 'below' : expected > marketAvg * 1.1 ? 'above' : 'at'
                    const topMatches = roleData.matches.slice(0, 10)

                    return (
                      <div className="match-role-section" key={role}>
                        <div className="match-role-header">
                          <div className="match-role-title">
                            {t(`cat.${role}` as MessageKey)} · {t('ai.topOf', { shown: topMatches.length, total: roleData.matches.length })}
                          </div>
                          {marketAvg > 0 && (
                            <div className="match-salary-info">
                              {t('ai.marketAvg', { v: `${formatTenge(marketAvg)} ₸` })}
                              {status && <>&nbsp;<span className={`salary-status salary-status--${status}`}>{t(`ai.salary.${status}`)}</span></>}
                            </div>
                          )}
                        </div>
                        {roleData.matches.length === 0 && <div className="empty-state"><p>{t('ai.noMatches')}</p></div>}
                        {topMatches.map((match) => (
                          <MatchCard key={match.job.id} match={match} saved={savedIds.has(match.job.id)}
                                     onSave={save} onGenerateCv={openCVModal} />
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

