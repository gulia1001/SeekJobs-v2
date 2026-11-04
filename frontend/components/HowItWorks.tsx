'use client'
import { useEffect, useRef } from 'react'
import { useI18n } from '@/lib/i18n'

const STEPS = [
  { n: '01', icon: '📄', title: 'steps.1.title', text: 'steps.1.text' },
  { n: '02', icon: '🎯', title: 'steps.2.title', text: 'steps.2.text' },
  { n: '03', icon: '✨', title: 'steps.3.title', text: 'steps.3.text' },
] as const

export default function HowItWorks() {
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
    <section className="steps-section reveal" ref={ref}>
      <div className="section-label">{t('steps.label')}</div>
      <h2>{t('steps.title1')}<br /><em>{t('steps.title2')}</em></h2>

      <div className="steps-grid">
        {STEPS.map((s) => (
          <div className="step" data-n={s.n} key={s.n}>
            <div className="step-icon">{s.icon}</div>
            <h3>{t(s.title)}</h3>
            <p>{t(s.text)}</p>
          </div>
        ))}
      </div>
    </section>
  )
}
