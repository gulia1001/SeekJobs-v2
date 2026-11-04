'use client'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import en, { type MessageKey } from './messages/en'
import kk from './messages/kk'
import ru from './messages/ru'

export type Lang = 'ru' | 'kk' | 'en'
export type { MessageKey }

const DICTS: Record<Lang, Record<MessageKey, string>> = { ru, kk, en }
export const LANGS: { code: Lang; label: string }[] = [
  { code: 'ru', label: 'RU' },
  { code: 'kk', label: 'ҚАЗ' },
  { code: 'en', label: 'EN' },
]
const STORAGE_KEY = 'seekjobs.lang'
const DEFAULT_LANG: Lang = 'ru' // most vacancies and users in Kazakhstan's IT market use Russian

type Vars = Record<string, string | number>
type I18n = { lang: Lang; setLang: (l: Lang) => void; t: (key: MessageKey, vars?: Vars) => string }

const I18nContext = createContext<I18n | null>(null)

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'ru' || saved === 'kk' || saved === 'en') return saved
  } catch { /* storage blocked */ }
  const browser = (typeof navigator !== 'undefined' ? navigator.language : '').toLowerCase()
  if (browser.startsWith('kk')) return 'kk'
  if (browser.startsWith('en')) return 'en'
  return DEFAULT_LANG
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(DEFAULT_LANG) // server render uses the default

  useEffect(() => { setLangState(initialLang()) }, [])
  useEffect(() => { document.documentElement.lang = lang }, [lang])

  const setLang = useCallback((l: Lang) => {
    setLangState(l)
    try { localStorage.setItem(STORAGE_KEY, l) } catch { /* storage blocked */ }
  }, [])

  const t = useCallback((key: MessageKey, vars?: Vars) => {
    let s = DICTS[lang][key] ?? en[key] ?? key
    if (vars) for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(String(v))
    return s
  }, [lang])

  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t])
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n(): I18n {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error('useI18n must be used inside <LanguageProvider>')
  return ctx
}

/** 'today', 'yesterday', '5 days ago' in the current language; '' when unknown. */
export function usePostedAgo() {
  const { t } = useI18n()
  return useCallback((iso?: string | null) => {
    if (!iso) return ''
    const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000)
    if (Number.isNaN(days)) return ''
    if (days <= 0) return t('time.today')
    if (days === 1) return t('time.yesterday')
    return t('time.daysAgo', { n: days })
  }, [t])
}

/** 500000 -> "500 000" (the way salaries are written in Kazakhstan) */
export function formatTenge(n: number): string {
  return Math.round(n).toLocaleString('ru-RU').replace(/ /g, ' ')
}
