/**
 * Composable for the recruiter dashboard — fetches aggregated stats,
 * pipeline breakdown, recent applications, and top active jobs.
 * Read-only: no mutation methods needed.
 */
export function useDashboard() {
  const { data, status: fetchStatus, error, refresh } = useFetch('/api/dashboard/stats', {
    key: 'dashboard-stats',
    headers: useRequestHeaders(['cookie']),
  })

  /** Summary counts (open jobs, candidates, applications, unreviewed) */
  const counts = computed(() => data.value?.counts ?? {
    openJobs: 0,
    totalCandidates: 0,
    totalApplications: 0,
    newApplications: 0,
  })

  /** Application count per status */
  const pipeline = computed(() => data.value?.pipeline ?? {
    new: 0,
    screening: 0,
    interview: 0,
    offer: 0,
    hired: 0,
    rejected: 0,
  })

  /** Job count per status */
  const jobsByStatus = computed(() => data.value?.jobsByStatus ?? {
    draft: 0,
    open: 0,
    closed: 0,
    archived: 0,
  })

  /** Last 10 applications with candidate + job info */
  const recentApplications = computed(() => data.value?.recentApplications ?? [])

  /** Top 5 open jobs sorted by application count */
  const topJobs = computed(() => data.value?.topJobs ?? [])

  return {
    counts,
    pipeline,
    jobsByStatus,
    recentApplications,
    topJobs,
    fetchStatus,
    error,
    refresh,
  }
}
