'use client'

export default function Nav() {
  return (
    <nav>
      <a className="logo" href="#">
        <span className="logo-dot" />
        Job<em style={{ fontFamily: "'Instrument Serif', serif", fontStyle: 'italic', color: 'var(--accent)' }}>SeekJobs</em>
      </a>
      <ul className="nav-links">
        <li><a href="#jobs">Vacancies</a></li>
        <li><a href="#ai-agent">AI Agent</a></li>
        <li><a href="#features">Features</a></li>
        <li><a href="#ai-agent" className="nav-cta">Get Started</a></li>
      </ul>
    </nav>
  )
}
