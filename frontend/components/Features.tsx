'use client'
import { useEffect, useRef } from 'react'

const FEATURES = [
  { icon: '🧠', title: 'Semantic Skill Matching', desc: 'Goes beyond keywords. Our AI understands context — "built microservices" matches distributed-systems roles, not just Node.js listings.' },
  { icon: '📊', title: 'KZ Salary Intelligence', desc: 'Each match includes real salary benchmarks from HH.kz, Kolesa, Kaspi, and Telegram IT channels — so you know your market worth.' },
  { icon: '⚡', title: 'Real-Time Vacancies', desc: 'Aggregated from the top KZ job boards and Telegram channels, refreshed daily via Airflow pipeline. Never miss a fresh opening.' },
  { icon: '🔀', title: 'Multi-Role Strategy', desc: 'Pivot between DevOps and Backend, or Data Engineer and ML Engineer in one session. Get separate match lists and CVs for each track.' },
  { icon: '🐙', title: 'GitHub Project Analysis', desc: 'We read your repos, detect your stack, and surface projects that matter — so your CV reflects what you actually built, not just what you listed.' },
  { icon: '🔗', title: 'LinkedIn + CV Fusion', desc: 'Combine your uploaded CV, LinkedIn experience, and GitHub activity into one unified profile. The AI fills the gaps between all three sources.' },
]

export default function Features() {
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
    <section id="features" className="features-section reveal" ref={ref}>
      <div className="section-label">Why SeekJobs</div>
      <h2>Built for the<br /><em>modern job hunt</em></h2>

      <div className="features-grid">
        {FEATURES.map((f) => (
          <div className="feature" key={f.title}>
            <div className="feature-icon">{f.icon}</div>
            <h3>{f.title}</h3>
            <p>{f.desc}</p>
          </div>
        ))}
      </div>
    </section>
  )
}
