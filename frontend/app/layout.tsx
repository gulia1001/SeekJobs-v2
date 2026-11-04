import type { Metadata } from 'next'
import './globals.css'
import Providers from './providers'

export const metadata: Metadata = {
  title: 'SeekJobs — IT jobs in Kazakhstan that fit your CV',
  description: 'Fresh IT vacancies from Kazakhstan’s Telegram channels, matched to your CV, with skill gaps, salaries and a tailored CV for each job.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
