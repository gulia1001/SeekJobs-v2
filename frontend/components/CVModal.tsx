'use client'
import { useEffect } from 'react'
import type { GeneratedCV } from '@/lib/types'

interface Props {
  cv: GeneratedCV | null
  jobTitle: string
  company: string
  onClose: () => void
}

export default function CVModal({ cv, jobTitle, company, onClose }: Props) {
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose])

  const downloadTex = () => {
    if (!cv?.latex) return
    const blob = new Blob([cv.latex], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `CV_${cv.name?.replace(/\s+/g, '_')}_${jobTitle.replace(/\s+/g, '_')}.tex`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  return (
    <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="modal">
        <div className="modal-header">
          <div className="modal-title">Tailored CV — {jobTitle}</div>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">
          {!cv ? (
            <div className="cv-loading">
              <div className="loading-spinner" />
              Generating your tailored CV...
            </div>
          ) : (
            <>
              <div className="modal-actions">
                <button
                  className="btn-primary"
                  style={{ flex: 2, padding: '10px', fontSize: 12 }}
                  onClick={() => window.print()}
                >
                  📄 Print / Save PDF
                </button>
                <button
                  className="btn-ghost"
                  style={{ flex: 1, padding: '10px', fontSize: 12 }}
                  onClick={downloadTex}
                >
                  💾 .TEX
                </button>
                <button
                  className="btn-ghost"
                  style={{ flex: 1, padding: '10px', fontSize: 12, opacity: 0.7 }}
                  onClick={onClose}
                >
                  Close
                </button>
              </div>

              <div id="cv-print-area" className="cv-preview">
                <div className="cv-name">{cv.name || 'Your Name'}</div>
                <div className="cv-role">{cv.role}</div>

                <div className="cv-contact">
                  {cv.email && <span className="cv-contact-item">✉ {cv.email}</span>}
                  {cv.linkedin && <span className="cv-contact-item">🔗 <a href={cv.linkedin} target="_blank" rel="noopener noreferrer">LinkedIn</a></span>}
                  {cv.github && <span className="cv-contact-item">💻 <a href={cv.github} target="_blank" rel="noopener noreferrer">GitHub</a></span>}
                </div>

                <div className="cv-section-title">Professional Summary</div>
                <div style={{ fontSize: 12, color: '#444', lineHeight: 1.8 }}>{cv.summary}</div>

                {(cv.experience?.length ?? 0) > 0 && (
                  <>
                    <div className="cv-section-title">Experience</div>
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
                    <div className="cv-section-title">Key Projects (GitHub)</div>
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
                    <div className="cv-section-title">Education</div>
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
                    <div className="cv-section-title">Technical Skills</div>
                    <div className="cv-skills-grid">
                      {cv.skills?.map((s) => <span className="cv-skill" key={s}>{s}</span>)}
                    </div>
                  </>
                )}

                {(cv.certificates?.length ?? 0) > 0 && (
                  <>
                    <div className="cv-section-title">Certifications</div>
                    <ul className="cv-list">
                      {cv.certificates?.map((cert, i) => <li key={i}>{cert}</li>)}
                    </ul>
                  </>
                )}

                <div className="cv-tailored-note">
                  ✨ This CV was tailored specifically for <strong>{jobTitle}</strong> at <strong>{company}</strong>. Keywords, skill order, and experience framing are optimised for this role. This is a one-page document optimised for ATS scanning.
                </div>

                {cv.latex && (
                  <div className="cv-latex-notice" style={{ marginTop: 16, padding: 8, backgroundColor: '#f5f5f5', borderRadius: 4, fontSize: 11, color: '#666', textAlign: 'center' }}>
                    💾 A pro-level .TEX file is also ready. You can download it to use on Overleaf.
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
