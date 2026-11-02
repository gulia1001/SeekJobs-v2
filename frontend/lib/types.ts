export interface Job {
  id: string
  title: string
  company: string
  city: string
  category: string
  level: string
  work_format: string
  salary_from?: number
  salary_to?: number
  salary_avg?: number
  currency: string
  skills: string[]
  description?: string
  source: string
  url: string
  posted_at?: string | null
}

export interface Match {
  rank: number
  score: number
  job: Job
  reason: string
  skills_matched: string[]
  skills_missing: string[]
  skills_required: number
  salary_comparison: {
    user_expected?: number
    job_avg?: number
    market_avg?: number
    status: 'below' | 'at' | 'above' | 'unknown'
  }
}

export interface RoleResult {
  market_avg_salary: number
  currency: string
  matches: Match[]
}

export interface UserProfile {
  name?: string
  skills: string[]
  github_summary?: string
  linkedin_summary?: string
  github_url?: string
  linkedin_url?: string
  top_repos: { name: string; description: string; stack: string[]; stars: number; url: string }[]
  certifications: { name: string; authority: string }[]
  cv_text?: string
}

export interface AnalysisResult {
  profile: UserProfile
  by_role: Record<string, RoleResult>
}

export interface GeneratedCV {
  name: string
  role: string
  email?: string
  github?: string
  linkedin?: string
  summary: string
  experience: {
    title: string
    company: string
    period: string
    description: string
  }[]
  education: {
    degree: string
    school: string
    period: string
  }[]
  skills: string[]
  certificates?: string[]
  projects?: Array<{ name: string; description: string; tech: string }>
  latex: string
  tailored_note: string
}

export interface JobsResponse {
  jobs: Job[]
  total: number
  page: number
  pages: number
}
