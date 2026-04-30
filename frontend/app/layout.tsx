import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'SeekJobs — Seek Jobs. Land Faster.',
  description: 'AI-powered career intelligence for the KZ IT market. Match your profile, get tailored CVs.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
