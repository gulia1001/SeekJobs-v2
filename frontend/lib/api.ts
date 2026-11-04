import type {
  AnalysisResult, Application, ApplicationStatus, GeneratedCV, JobsResponse, Me, SavedProfile, Stats, User,
} from './types'

// Backend address, e.g. https://api.seekjobs.kz — set NEXT_PUBLIC_API_URL at build time.
const API_BASE = `${(process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8001').replace(/\/+$/, '')}/api/`
const TOKEN_KEY = 'seekjobs.token'

/** An API error with its HTTP status (0 = the server could not be reached), so screens can
 *  show a message in the user's language for the cases they know. */
export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch { /* storage blocked */ }
}

/** fetch + login token + readable errors (FastAPI sends {detail: string | [{msg}]}) */
async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, headers })
  } catch {
    throw new ApiError(0, `Network error: check that the backend is running at ${API_BASE}`)
  }
  if (!res.ok) {
    let message = `Server error ${res.status}`
    try {
      const body = await res.json()
      const detail = body?.detail
      if (typeof detail === 'string') message = detail
      else if (Array.isArray(detail)) message = detail.map((d) => d?.msg).filter(Boolean).join('; ') || message
    } catch { /* not JSON */ }
    throw new ApiError(res.status, message)
  }
  return res
}

const json = (body: unknown): RequestInit => ({
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

// ── jobs, matching, CVs ─────────────────────────────────────────────────────
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

export async function fetchStats(): Promise<Stats> {
  return (await request('stats')).json()
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
  return (await request('cv/generate', { method: 'POST', ...json(payload) })).json()
}

/** Server-rendered CV file (real text, so applicant-tracking systems can read it). */
export async function exportCV(cv: GeneratedCV, format: 'pdf' | 'docx'): Promise<Blob> {
  return (await request('cv/export', { method: 'POST', ...json({ cv, format }) })).blob()
}

// ── accounts ────────────────────────────────────────────────────────────────
export async function register(body: {
  email: string; password: string; name: string; language: string; consent: boolean
}): Promise<{ token: string; user: User }> {
  return (await request('auth/register', { method: 'POST', ...json(body) })).json()
}

export async function login(email: string, password: string): Promise<{ token: string; user: User }> {
  return (await request('auth/login', { method: 'POST', ...json({ email, password }) })).json()
}

export async function logout(): Promise<void> {
  await request('auth/logout', { method: 'POST' })
}

export async function getMe(): Promise<Me> {
  return (await request('me')).json()
}

export async function updateMe(body: { name?: string; language?: string }): Promise<{ user: User }> {
  return (await request('me', { method: 'PATCH', ...json(body) })).json()
}

export async function deleteMe(): Promise<void> {
  await request('me', { method: 'DELETE' })
}

export async function saveProfile(body: {
  skills: string[]; level: string; target_roles: string[]; preferred_salary: number | null
  cv_text: string; github_url: string; linkedin_url: string
}): Promise<{ profile: SavedProfile }> {
  return (await request('me/profile', { method: 'PUT', ...json(body) })).json()
}

export async function getMyMatches(): Promise<AnalysisResult & { profile: SavedProfile }> {
  return (await request('me/matches')).json()
}

// ── application tracker ─────────────────────────────────────────────────────
export async function listApplications(): Promise<{ applications: Application[]; statuses: ApplicationStatus[] }> {
  return (await request('me/applications')).json()
}

export async function addApplication(jobId: string, status: ApplicationStatus = 'saved'): Promise<{ application: Application }> {
  return (await request('me/applications', { method: 'POST', ...json({ job_id: jobId, status }) })).json()
}

export async function updateApplication(id: number, body: { status?: ApplicationStatus; notes?: string }): Promise<{ application: Application }> {
  return (await request(`me/applications/${id}`, { method: 'PATCH', ...json(body) })).json()
}

export async function deleteApplication(id: number): Promise<void> {
  await request(`me/applications/${id}`, { method: 'DELETE' })
}

// ── Telegram ────────────────────────────────────────────────────────────────
export async function telegramLink(): Promise<{ url: string; expires_in_minutes: number }> {
  return (await request('me/telegram', { method: 'POST' })).json()
}

export async function telegramUnlink(): Promise<void> {
  await request('me/telegram', { method: 'DELETE' })
}
