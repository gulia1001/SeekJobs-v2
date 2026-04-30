export default function Hero() {
  return (
    <div className="hero">
      <div className="hero-grid" />
      <div className="hero-glow" />

      <div className="hero-badge">
        <span />
        AI-Powered Career Intelligence · KZ IT Market
      </div>

      <h1>
        Seek Jobs.<br />
        <em>Land Faster.</em>
      </h1>

      <p className="hero-sub">
        Drop your CV, paste your LinkedIn &amp; GitHub — our AI matches you with top roles in Kazakhstan and generates a tailored resume for each.
      </p>

      <div className="hero-actions">
        <a href="#ai-agent" className="btn-primary">⚡ Try the AI Agent</a>
        <a href="#jobs" className="btn-ghost">Browse Vacancies</a>
      </div>

      <div className="hero-stats">
        <div>
          <div className="stat-num">7,000+</div>
          <div className="stat-label">Active Vacancies</div>
        </div>
        <div>
          <div className="stat-num">500k</div>
          <div className="stat-label">Median Salary</div>
        </div>
        <div>
          <div className="stat-num">1 min</div>
          <div className="stat-label">To Your Top Matches</div>
        </div>
        <div>
          <div className="stat-num">10×</div>
          <div className="stat-label">Faster Applications</div>
        </div>
      </div>
    </div>
  )
}
