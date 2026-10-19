import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { errorMessage } from '@/components/ui/feedback'
import { followupsService, leadsService, metricsService, runsService } from '@/services/api-services'
import type { LeadFilters, RunStatus } from '@/types/api'

export const keys = {
  overview: ['overview'] as const,
  leads: (f: LeadFilters) => ['leads', f] as const,
  lead: (id: string) => ['lead', id] as const,
  runs: (p: object) => ['runs', p] as const,
  followups: (p: object) => ['followups', p] as const,
  history: (id: string) => ['followup-history', id] as const,
}

export const useOverview = () => useQuery({ queryKey: keys.overview, queryFn: () => metricsService.overview(), refetchInterval: 30_000 })

export const useLeads = (filters: LeadFilters) =>
  useQuery({ queryKey: keys.leads(filters), queryFn: () => leadsService.list(filters), placeholderData: keepPreviousData })

export const useLead = (id: string) =>
  useQuery({ queryKey: keys.lead(id), queryFn: () => leadsService.get(id), refetchInterval: 15_000 })

export const useRuns = (p: { page: number; status?: RunStatus | ''; workflow?: string }) =>
  useQuery({
    queryKey: keys.runs(p),
    queryFn: () => runsService.list({ ...p, page_size: 15 }),
    placeholderData: keepPreviousData,
    refetchInterval: 15_000,
  })

export const useFollowups = (p: { status: 'DRAFT' | 'APPROVED' | 'REJECTED' | ''; page: number }) =>
  useQuery({
    queryKey: keys.followups(p),
    queryFn: () => followupsService.list({ ...p, page_size: 20 }),
    placeholderData: keepPreviousData,
  })

export const useFollowupHistory = (id: string | null) =>
  useQuery({ queryKey: keys.history(id ?? ''), queryFn: () => followupsService.history(id as string), enabled: Boolean(id) })

function onError(e: unknown) {
  const { title, detail } = errorMessage(e)
  toast.error(title, { description: detail })
}

function useInvalidate() {
  const qc = useQueryClient()
  return () =>
    Promise.all(
      ['followups', 'lead', 'leads', 'overview', 'runs', 'followup-history'].map((k) => qc.invalidateQueries({ queryKey: [k] })),
    )
}

export function useRetryLead() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (id: string) => leadsService.retry(id),
    onSuccess: () => {
      toast.success('Relance planifiée', { description: 'Le prochain passage du workflow de supervision la prendra en charge.' })
      return invalidate()
    },
    onError,
  })
}

export function useRetryRun() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (id: string) => runsService.retry(id),
    onSuccess: () => {
      toast.success('Reprise manuelle planifiée')
      return invalidate()
    },
    onError,
  })
}

export function useApproveFollowup() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (v: { id: string; version?: number }) => followupsService.approve(v.id, v.version),
    onSuccess: () => {
      toast.success('Brouillon approuvé', { description: 'Aucun e-mail n’a été envoyé : l’envoi n’existe pas dans cette version.' })
      return invalidate()
    },
    onError,
  })
}

export function useRejectFollowup() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (v: { id: string; reason?: string }) => followupsService.reject(v.id, v.reason),
    onSuccess: () => {
      toast.success('Brouillon rejeté')
      return invalidate()
    },
    onError,
  })
}

export function useEditFollowup() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (v: { id: string; subject: string; body: string; version: number }) =>
      followupsService.patch(v.id, { subject: v.subject, body: v.body, expected_version: v.version }),
    onSuccess: () => {
      toast.success('Modifications enregistrées')
      return invalidate()
    },
    onError,
  })
}
