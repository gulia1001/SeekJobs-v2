'use client'
import { useEffect, useRef } from 'react'
import { useI18n } from '@/lib/i18n'

const FEATURES = [
  { icon: '⚡', n: 1 },
  { icon: '🎯', n: 2 },
  { icon: '🧩', n: 3 },
  { icon: '₸', n: 4 },
  { icon: '📄', n: 5 },
  { icon: '✈️', n: 6 },
] as const

export default function Features() {
  const { t } = useI18n()
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
      <div className="section-label">{t('features.label')}</div>
      <h2>{t('features.title1')}<br /><em>{t('features.title2')}</em></h2>

      <div className="features-grid">
        {FEATURES.map((f) => (
          <div className="feature" key={f.n}>
            <div className="feature-icon">{f.icon}</div>
            <h3>{t(`features.${f.n}.title`)}</h3>
            <p>{t(`features.${f.n}.text`)}</p>
          </div>
        ))}
      </div>
    </section>
  )
}
