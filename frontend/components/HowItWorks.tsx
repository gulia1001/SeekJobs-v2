'use client'
import { useEffect, useRef } from 'react'

export default function HowItWorks() {
  const ref = useRef<HTMLElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { el.classList.add('visible'); observer.disconnect() } },
      { threshold: 0.1 }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return (
    <section className="steps-section reveal" ref={ref}>
      <div className="section-label">How It Works</div>
      <h2>Three steps to your<br /><em>next opportunity</em></h2>

      <div className="steps-grid">
        <div className="step" data-n="01">
          <div className="step-icon">📄</div>
          <h3>Upload Your Profile</h3>
          <p>Share your CV, LinkedIn URL, and GitHub profile. Our AI extracts your skills, experience, and achievements across all sources.</p>
        </div>
        <div className="step" data-n="02">
          <div className="step-icon">🎯</div>
          <h3>Pick Your Roles</h3>
          <p>Select one or more target tracks — DevOps, Backend, Data Engineer, and more. Our engine ranks every KZ IT vacancy against your profile.</p>
        </div>
        <div className="step" data-n="03">
          <div className="step-icon">✨</div>
          <h3>Get Tailored CVs</h3>
          <p>For each matched role you get an AI-rewritten CV — keywords, skill order, and framing optimised for that specific job and stack.</p>
        </div>
      </div>
    </section>
  )
}
