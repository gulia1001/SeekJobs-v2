'use client'
import { useCallback, useEffect, useState } from 'react'
import { addApplication, listApplications } from './api'
import { useAuth } from './auth'

/** Which jobs the logged-in user already tracks, and a way to save one more. */
export function useSavedJobs() {
  const { user, openLogin } = useAuth()
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (!user) { setSavedIds(new Set()); return }
    listApplications()
      .then(({ applications }) => setSavedIds(new Set(applications.map((a) => a.job_id))))
      .catch(() => {})
  }, [user])

  const save = useCallback(async (jobId: string) => {
    if (!user) { openLogin(); return }
    await addApplication(jobId)
    setSavedIds((prev) => new Set(prev).add(jobId))
  }, [user, openLogin])

  return { savedIds, save }
}
