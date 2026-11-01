import type { AnalysisResult, GeneratedCV, JobsResponse } from './types'

// Backend address, e.g. https://api.seekjobs.kz — set NEXT_PUBLIC_API_URL at build time.
const API_BASE = `${(process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8001').replace(/\/+$/, '')}/api/`

/** fetch + readable error messages (FastAPI sends {detail: string | [{msg}]}) */
async function request(path: string, init?: RequestInit): Promise<Response> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, init)
  } catch {
    throw new Error(`Network error — check that the backend is running at ${API_BASE}`)
  }
  if (!res.ok) {
    let message = `Server error ${res.status}`
    try {
      const body = await res.json()
      const detail = body?.detail
      if (typeof detail === 'string') message = detail
      else if (Array.isArray(detail)) message = detail.map((d) => d?.msg).filter(Boolean).join('; ') || message
    } catch { /* not JSON */ }
    throw new Error(message)
  }
  return res
}

export async function fetchJobs(params: {
  page?: number
  limit?: number
  category?: string
  level?: string
  format?: string
}): Promise<JobsResponse> {
  const query = new URLSearchParams()
  query.set('page', String(params.page ?? 1))
  query.set('limit', String(params.limit ?? 12))
  if (params.category && params.category !== 'all') query.set('category', params.category)
  if (params.level && params.level !== 'all') query.set('level', params.level)
  if (params.format && params.format !== 'all') query.set('format', params.format)
  return (await request(`jobs?${query}`)).json()
}

export async function analyzeProfile(formData: FormData): Promise<AnalysisResult> {
  // the browser sets the multipart Content-Type (with boundary) for FormData
  return (await request('analyze', { method: 'POST', body: formData })).json()
}

export async function generateCV(payload: {
  job_id: string
  job_title: string
  job_skills: string[]
  user_profile: unknown
  cv_text?: string
}): Promise<GeneratedCV> {
  const res = await request('cv/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return res.json()
}

/** Server-rendered CV file (real text, so applicant-tracking systems can read it). */
export async function exportCV(cv: GeneratedCV, format: 'pdf' | 'docx'): Promise<Blob> {
  const res = await request('cv/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cv, format }),
  })
  return res.blob()
}
