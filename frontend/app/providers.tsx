'use client'
import type { ReactNode } from 'react'
import AuthModal from '@/components/AuthModal'
import { AuthProvider } from '@/lib/auth'
import { LanguageProvider } from '@/lib/i18n'

export default function Providers({ children }: { children: ReactNode }) {
  return (
    <LanguageProvider>
      <AuthProvider>
        {children}
        <AuthModal />
      </AuthProvider>
    </LanguageProvider>
  )
}
