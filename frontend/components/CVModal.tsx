'use client'
import { useEffect, useState } from 'react'
import type { GeneratedCV } from '@/lib/types'
import { exportCV } from '@/lib/api'
import { useI18n } from '@/lib/i18n'

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

const safe = (s: string) => s.trim().replace(/[\\/:*?"<>|\s]+/g, '_')

interface Props {
  cv: GeneratedCV | null
  jobTitle: string
  company: string
  onClose: () => void
}

export default function CVModal({ cv, jobTitle, company, onClose }: Props) {
  const { t } = useI18n()
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose])

  const [downloading, setDownloading] = useState<'' | 'pdf' | 'docx'>('')
  const [downloadError, setDownloadError] = useState('')
  const fileBase = `CV_${safe(cv?.name || 'CV')}_${safe(jobTitle)}`

  const download = async (format: 'pdf' | 'docx') => {
    if (!cv) return
    setDownloading(format)
    setDownloadError('')
    try {
      saveBlob(await exportCV(cv, format), `${fileBase}.${format}`)
    } catch (e: unknown) {
      setDownloadError(t('cv.downloadFailed', { msg: e instanceof Error ? e.message : String(e) }))
    } finally {
      setDownloading('')
    }
  }

  const downloadTex = () => {
    if (!cv?.latex) return
    saveBlob(new Blob([cv.latex], { type: 'text/plain' }), `${fileBase}.tex`)
  }

  return (
    <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="modal">
        <div className="modal-header">
          <div className="modal-title">{t('cv.title', { job: jobTitle })}</div>
          <button className="modal-close" onClick={onClose} aria-label={t('cv.close')}>✕</button>
        </div>
        <div className="modal-body">
          {!cv ? (
            <div className="cv-loading">
              <div className="loading-spinner" />
              {t('cv.generating')}
            </div>
          ) : (
            <>
              <div className="modal-actions">
                <button
                  className="btn-primary"
                  style={{ flex: 2, padding: '10px', fontSize: 12 }}
                  onClick={() => download('pdf')}
                  disabled={downloading !== ''}
                >
                  {downloading === 'pdf' ? t('cv.preparing') : t('cv.pdf')}
                </button>
                <button
                  className="btn-ghost"
                  style={{ flex: 1, padding: '10px', fontSize: 12 }}
                  onClick={() => download('docx')}
                  disabled={downloading !== ''}
                >
                  {downloading === 'docx' ? t('cv.preparing') : t('cv.word')}
                </button>
                {cv.latex && (
                  <button
                    className="btn-ghost"
                    style={{ flex: 1, padding: '10px', fontSize: 12 }}
                    onClick={downloadTex}
                  >
                    .TEX
                  </button>
                )}
                <button
                  className="btn-ghost"
                  style={{ flex: 1, padding: '10px', fontSize: 12, opacity: 0.7 }}
                  onClick={onClose}
                >
                  {t('cv.close')}
                </button>
              </div>
              {cv.ai_limit_reached && <div className="form-note">ℹ {t('cv.limit')}</div>}
              {downloadError && (
                <div style={{ color: 'var(--accent)', fontSize: 12, margin: '4px 0 8px' }}>⚠ {downloadError}</div>
              )}

              <div id="cv-print-area" className="cv-preview">
                <div className="cv-name">{cv.name}</div>
                <div className="cv-role">{cv.role}</div>

                <div className="cv-contact">
                  {cv.email && <span className="cv-contact-item">✉ {cv.email}</span>}
                  {cv.linkedin && <span className="cv-contact-item">🔗 <a href={cv.linkedin} target="_blank" rel="noopener noreferrer">LinkedIn</a></span>}
                  {cv.github && <span className="cv-contact-item">💻 <a href={cv.github} target="_blank" rel="noopener noreferrer">GitHub</a></span>}
                </div>

                <div className="cv-section-title">{t('cv.summary')}</div>
                <div style={{ fontSize: 12, color: '#444', lineHeight: 1.8 }}>{cv.summary}</div>

                {(cv.experience?.length ?? 0) > 0 && (
                  <>
                    <div className="cv-section-title">{t('cv.experience')}</div>
                    {cv.experience?.map((exp, i) => (
                      <div className="cv-entry" key={i}>
                        <div className="cv-entry-title">
                          <span>{exp.title} — {exp.company}</span>
                          <span className="cv-entry-meta">{exp.period}</span>
                        </div>
                        <div className="cv-entry-desc">{exp.description}</div>
                      </div>
                    ))}
                  </>
                )}

                {(cv.projects?.length ?? 0) > 0 && (
                  <>
                    <div className="cv-section-title">{t('cv.projects')}</div>
                    {cv.projects?.map((proj, i) => (
                      <div className="cv-entry" key={i}>
                        <div className="cv-entry-title">
                          <span>{proj.name}</span>
                          <span className="cv-entry-meta">{proj.tech}</span>
                        </div>
                        <div className="cv-entry-desc">{proj.description}</div>
                      </div>
                    ))}
                  </>
                )}

                {(cv.education?.length ?? 0) > 0 && (
                  <>
                    <div className="cv-section-title">{t('cv.education')}</div>
                    {cv.education?.map((edu, i) => (
                      <div className="cv-entry" key={i}>
                        <div className="cv-entry-title">
                          <span>{edu.degree}</span>
                          <span className="cv-entry-meta">{edu.period}</span>
                        </div>
                        <div className="cv-entry-meta" style={{ fontStyle: 'normal' }}>{edu.school}</div>
                      </div>
                    ))}
                  </>
                )}

                {(cv.skills?.length ?? 0) > 0 && (
                  <>
                    <div className="cv-section-title">{t('cv.skills')}</div>
                    <div className="cv-skills-grid">
                      {cv.skills?.map((s) => <span className="cv-skill" key={s}>{s}</span>)}
                    </div>
                  </>
                )}

                {(cv.certificates?.length ?? 0) > 0 && (
                  <>
                    <div className="cv-section-title">{t('cv.certs')}</div>
                    <ul className="cv-list">
                      {cv.certificates?.map((cert, i) => <li key={i}>{cert}</li>)}
                    </ul>
                  </>
                )}

                <div className="cv-tailored-note">
                  ✨ {t('cv.note', { job: jobTitle, company: company || '—' })}
                </div>

                {cv.latex && (
                  <div className="cv-latex-notice" style={{ marginTop: 16, padding: 8, backgroundColor: '#f5f5f5', borderRadius: 4, fontSize: 11, color: '#666', textAlign: 'center' }}>
                    💾 {t('cv.texNote')}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
