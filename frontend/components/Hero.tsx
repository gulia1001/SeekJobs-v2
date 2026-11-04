'use client'
import { useEffect, useState } from 'react'
import { fetchStats } from '@/lib/api'
import { formatTenge, usePostedAgo, useI18n } from '@/lib/i18n'
import type { Stats } from '@/lib/types'

export default function Hero() {
  const { t } = useI18n()
  const postedAgo = usePostedAgo()
  const [stats, setStats] = useState<Stats | null>(null)

  useEffect(() => { fetchStats().then(setStats).catch(() => setStats(null)) }, [])

  // real numbers from the API; a dash while loading or when the backend is offline
  const items = [
    { value: stats ? formatTenge(stats.active_jobs) : '—', label: t('hero.stat.jobs') },
    { value: stats?.median_salary_kzt ? `${Math.round(stats.median_salary_kzt / 1000)}k` : '—', label: t('hero.stat.salary') },
    { value: stats ? String(stats.sources || '—') : '—', label: t('hero.stat.sources') },
    { value: postedAgo(stats?.newest_post_at) || '—', label: t('hero.stat.updated') },
  ]

  return (
    <div className="hero">
      <div className="hero-grid" />
      <div className="hero-glow" />

      <div className="hero-badge">
        <span />
        {t('hero.badge')}
      </div>

      <h1>
        {t('hero.title1')}<br />
        <em>{t('hero.title2')}</em>
      </h1>

      <p className="hero-sub">{t('hero.sub')}</p>

      <div className="hero-actions">
        <a href="#ai-agent" className="btn-primary">{t('hero.try')}</a>
        <a href="#jobs" className="btn-ghost">{t('hero.browse')}</a>
      </div>

      <div className="hero-stats">
        {items.map((s) => (
          <div key={s.label}>
            <div className="stat-num">{s.value}</div>
            <div className="stat-label">{s.label}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
