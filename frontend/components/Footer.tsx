'use client'
import { useI18n } from '@/lib/i18n'
import { Logo } from './Nav'

export default function Footer() {
  const { t } = useI18n()
  return (
    <footer>
      <div className="footer-logo"><Logo /></div>
      <div className="footer-copy">
        {t('footer.copy')} · <a href="/privacy">{t('footer.privacy')}</a>
      </div>
    </footer>
  )
}
