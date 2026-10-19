import { apiFetch, setCsrfToken } from '@/lib/api'
import type {
  Followup,
  FollowupReviewItem,
  AuditEvent,
  LeadDetail,
  LeadFilters,
  LeadListItem,
  LeadReceipt,
  Overview,
  Page,
  Run,
  RunStatus,
  SessionInfo,
} from '@/types/api'

// --- Authentification -----------------------------------------------------------------------------
export const authService = {
  async me(): Promise<SessionInfo | null> {
    try {
      const s = await apiFetch<SessionInfo>('/v1/auth/me', { silentUnauthorized: true, retries: 1 })
      setCsrfToken(s.csrf_token)
      return s
    } catch (e) {
      if (e instanceof Error && 'status' in e && (e as { status: number }).status === 401) return null
      throw e
    }
  },
  async login(email: string, password: string): Promise<SessionInfo> {
    const s = await apiFetch<SessionInfo>('/v1/auth/login', {
      method: 'POST',
      body: { email, password },
      silentUnauthorized: true,
    })
    setCsrfToken(s.csrf_token)
    return s
  },
  async logout(): Promise<void> {
    try {
      await apiFetch<void>('/v1/auth/logout', { method: 'POST', silentUnauthorized: true })
    } finally {
      setCsrfToken(null)
    }
  },
}

// --- Formulaire public ------------------------------------------------------------------------------
export interface PublicLeadInput {
  full_name: string
  email: string
  company?: string | null
  phone?: string | null
  requested_service: string
  message: string
  consent_privacy: boolean
  consent_marketing: boolean
  website?: string
}
export const publicService = {
  submitLead: (input: PublicLeadInput, idempotencyKey: string) =>
    apiFetch<LeadReceipt>('/v1/public/leads', { method: 'POST', body: input, idempotencyKey }),
}

// --- Dashboard --------------------------------------------------------------------------------------
export const leadsService = {
  list: (f: LeadFilters) =>
    apiFetch<Page<LeadListItem>>('/v1/leads', {
      query: { ...f, review: f.review === undefined ? undefined : String(f.review) },
    }),
  get: (id: string) => apiFetch<LeadDetail>(`/v1/leads/${id}`),
  retry: (id: string) => apiFetch<{ lead_id: string; event_id: string; status: string }>(`/v1/leads/${id}/retry`, { method: 'POST' }),
}

export const metricsService = {
  overview: (days = 14) => apiFetch<Overview>('/v1/metrics/overview', { query: { days } }),
}

export const runsService = {
  list: (p: { page?: number; page_size?: number; status?: RunStatus | ''; workflow?: string; lead_id?: string }) =>
    apiFetch<Page<Run>>('/v1/automation-runs', { query: p }),
  retry: (id: string) => apiFetch<{ event_id: string; status: string }>(`/v1/automation-runs/${id}/retry`, { method: 'POST' }),
}

export const followupsService = {
  list: (p: { status?: 'DRAFT' | 'APPROVED' | 'REJECTED' | ''; page?: number; page_size?: number }) =>
    apiFetch<Page<FollowupReviewItem>>('/v1/followups', { query: p }),
  history: (id: string) => apiFetch<AuditEvent[]>(`/v1/followups/${id}/history`),
  patch: (id: string, body: { subject?: string; body?: string; expected_version?: number }) =>
    apiFetch<Followup>(`/v1/followups/${id}`, { method: 'PATCH', body }),
  approve: (id: string, expectedVersion?: number) =>
    apiFetch<Followup>(`/v1/followups/${id}/approve`, { method: 'POST', body: { expected_version: expectedVersion } }),
  reject: (id: string, reason?: string) =>
    apiFetch<Followup>(`/v1/followups/${id}/reject`, { method: 'POST', body: { reason: reason || undefined } }),
}
