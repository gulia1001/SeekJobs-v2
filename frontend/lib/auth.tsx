'use client'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import * as api from './api'
import { useI18n, type Lang } from './i18n'
import type { Me, User } from './types'

type Auth = {
  user: User | null
  me: Me | null
  ready: boolean // false until the saved login has been checked
  login: (email: string, password: string) => Promise<void>
  register: (body: { email: string; password: string; name: string; consent: boolean }) => Promise<void>
  logout: () => Promise<void>
  refresh: () => Promise<void>
  changeLanguage: (l: Lang) => void
  openLogin: () => void
  closeLogin: () => void
  loginOpen: boolean
}

const AuthContext = createContext<Auth | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const { lang, setLang } = useI18n()
  const [me, setMe] = useState<Me | null>(null)
  const [ready, setReady] = useState(false)
  const [loginOpen, setLoginOpen] = useState(false)

  const refresh = useCallback(async () => {
    if (!api.getToken()) { setMe(null); return }
    try {
      setMe(await api.getMe())
    } catch (e) {
      if (e instanceof api.ApiError && e.status === 401) { api.setToken(null); setMe(null) }
    }
  }, [])

  useEffect(() => { refresh().finally(() => setReady(true)) }, [refresh])

  const startSession = useCallback(async (token: string, user: User) => {
    api.setToken(token)
    setLang(user.language)
    await refresh()
    setLoginOpen(false)
  }, [refresh, setLang])

  const login = useCallback(async (email: string, password: string) => {
    const { token, user } = await api.login(email, password)
    await startSession(token, user)
  }, [startSession])

  const register = useCallback(async (body: { email: string; password: string; name: string; consent: boolean }) => {
    const { token, user } = await api.register({ ...body, language: lang })
    await startSession(token, user)
  }, [lang, startSession])

  const logout = useCallback(async () => {
    try { await api.logout() } catch { /* already logged out on the server */ }
    api.setToken(null)
    setMe(null)
  }, [])

  // the bot and the account use the same language as the site
  const changeLanguage = useCallback((l: Lang) => {
    setLang(l)
    if (me) api.updateMe({ language: l }).then(({ user }) => setMe((m) => (m ? { ...m, user } : m))).catch(() => {})
  }, [me, setLang])

  const value = useMemo<Auth>(() => ({
    user: me?.user ?? null, me, ready, login, register, logout, refresh, changeLanguage,
    openLogin: () => setLoginOpen(true), closeLogin: () => setLoginOpen(false), loginOpen,
  }), [me, ready, login, register, logout, refresh, changeLanguage, loginOpen])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): Auth {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
