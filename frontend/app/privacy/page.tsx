'use client'
import Footer from '@/components/Footer'
import Nav from '@/components/Nav'
import { useI18n, type MessageKey } from '@/lib/i18n'

const SECTIONS = ['what', 'why', 'third', 'where', 'rights', 'noAccount'] as const

export default function PrivacyPage() {
  const { t } = useI18n()
  return (
    <>
      <Nav />
      <main className="page-wrap prose-page">
        <h1 className="page-title">{t('privacy.title')}</h1>
        <p className="draft-banner">{t('privacy.draft')}</p>
        {SECTIONS.map((s) => (
          <section key={s}>
            <h2>{t(`privacy.${s}.title` as MessageKey)}</h2>
            <p>{t(`privacy.${s}.text` as MessageKey)}</p>
          </section>
        ))}
        <p><a href="/">{t('common.back')}</a></p>
      </main>
      <Footer />
    </>
  )
}
