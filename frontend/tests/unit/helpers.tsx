import { QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type * as React from 'react'
import { Toaster } from 'sonner'
import { createMemoryRouter, RouterProvider, type RouteObject } from 'react-router-dom'
import { AuthProvider, makeQueryClient, ThemeProvider } from '@/app/providers'
import type { LeadDetail, Role, SessionInfo } from '@/types/api'
import { vi } from 'vitest'

type Json = Record<string, unknown> | unknown[] | null

export interface MockRoute {
  method?: string
  path: string | RegExp
  status?: number
  body?: Json
  /** Fonction : calculée à chaque appel (permet de vérifier les requêtes reçues). */
  handler?: (req: { url: URL; init: RequestInit; json: unknown }) => { status?: number; body?: Json; delayMs?: number } | Promise<{ status?: number; body?: Json }>
  headers?: Record<string, string>
}

export interface RecordedCall {
  method: string
  url: URL
  headers: Record<string, string>
  json: unknown
}

/** Installe un `fetch` simulé. Retourne le journal des appels reçus. */
export function mockApi(routes: MockRoute[]) {
  const calls: RecordedCall[] = []
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.toString(), 'http://localhost')
    const method = (init.method ?? 'GET').toUpperCase()
    const headers = Object.fromEntries(Object.entries((init.headers ?? {}) as Record<string, string>))
    const json = init.body ? JSON.parse(init.body as string) : undefined
    calls.push({ method, url, headers, json })
    const route = routes.find(
      (r) => (r.method ?? 'GET').toUpperCase() === method && (typeof r.path === 'string' ? url.pathname === r.path : r.path.test(url.pathname)),
    )
    if (!route) return new Response(JSON.stringify({ error: { code: 'not_found', message: `no mock for ${method} ${url.pathname}` } }), { status: 404 })
    const out: { status?: number; body?: Json; delayMs?: number } = route.handler
      ? await route.handler({ url, init, json })
      : { status: route.status, body: route.body }
    if (out.delayMs) await new Promise((r) => setTimeout(r, out.delayMs))
    const status = out.status ?? 200
    return new Response(status === 204 ? null : JSON.stringify(out.body ?? {}), {
      status,
      headers: { 'Content-Type': 'application/json', 'X-Correlation-ID': 'corr-test-123', ...route.headers },
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  return { calls, fetchMock, count: (method: string, path: string | RegExp) => calls.filter((c) => c.method === method && (typeof path === 'string' ? c.url.pathname === path : path.test(c.url.pathname))).length }
}

export const session = (role: Role = 'SALES'): SessionInfo => ({
  user: { id: 'u1', email: `${role.toLowerCase()}@novadigital.example`, full_name: role === 'ADMIN' ? 'Ada Admin' : 'Sam Sales', role },
  csrf_token: 'csrf-test-token',
})

export const meRoute = (role: Role | null): MockRoute =>
  role ? { path: '/api/v1/auth/me', body: session(role) as unknown as Json } : { path: '/api/v1/auth/me', status: 401, body: { error: { code: 'not_authenticated', message: 'Authentification requise' } } }

export function renderRoutes(routes: RouteObject[], initialEntries: string[]) {
  const queryClient = makeQueryClient()
  const router = createMemoryRouter(routes, { initialEntries })
  const utils = render(
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <AuthProvider queryClient={queryClient}>
          <RouterProvider router={router} />
          <Toaster />
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>,
  )
  return { ...utils, router, queryClient }
}

export const renderPage = (ui: React.ReactElement, path = '/') => renderRoutes([{ path: '*', element: ui }], [path])

export function leadDetail(overrides: Partial<LeadDetail> = {}): LeadDetail {
  return {
    id: 'lead-1',
    created_at: '2026-10-19T09:00:00Z',
    status: 'READY',
    status_reason: null,
    source: 'website',
    requested_service: 'customer_support_automation',
    message: 'Bonjour <script>alert(1)</script> nous voulons automatiser le support.',
    is_demo: false,
    privacy_notice_version: '2026-10-v1',
    contact: { id: 'c1', full_name: 'Alice Martin', email: 'alice@example.org', company: 'Acme', phone: null, consent_status: 'granted', lead_count: 1 },
    qualification: {
      id: 'q1', version: 1, intent: 'automation', service: 'customer_support_automation', budget_amount: '3000.00', budget_currency: 'EUR',
      timeline_days: 30, language: 'fr', summary: 'Automatisation du support client', need_clarity: 'clear', score: 100, segment: 'HOT',
      score_explanation: {
        rule_version: 'scoring-v1', total: 100, segment: 'HOT', thresholds: { HOT: 75, WARM: 45 }, inputs_used: {},
        factors: [
          { id: 'service_known', label: 'Service du catalogue', max_points: 30, points: 30, awarded: true, detail: 'customer_support_automation (extrait du message)' },
          { id: 'budget_ok', label: 'Budget conforme', max_points: 25, points: 0, awarded: false, detail: 'aucun budget mentionné' },
        ],
      },
      extracted_data: { evidence: ['automatiser le support'] }, llm_provider: 'mock', model_name: 'mock-heuristic-1', prompt_version: 'mock-v1',
      scoring_rule_version: 'scoring-v1', human_review_required: false, review_reasons: [], created_at: '2026-10-19T09:00:05Z',
    },
    qualification_history: [{ version: 1, score: 100, segment: 'HOT', created_at: '2026-10-19T09:00:05Z', human_review_required: false }],
    crm: { provider: 'mock', external_contact_id: 'mock_1', sync_status: 'SYNCED', attempt_count: 1, last_error_code: null, last_synced_at: '2026-10-19T09:00:09Z' },
    followups: [],
    runs: [],
    audit: [],
    timeline: [
      { key: 'lead_received', label: 'Demande reçue', state: 'done', at: '2026-10-19T09:00:00Z', detail: 'Source : website' },
      { key: 'validated', label: 'Validation', state: 'done', at: '2026-10-19T09:00:00Z', detail: null },
      { key: 'ai_qualification', label: 'Qualification IA', state: 'done', at: '2026-10-19T09:00:05Z', detail: null },
      { key: 'scoring', label: 'Scoring', state: 'done', at: '2026-10-19T09:00:05Z', detail: '100/100' },
      { key: 'crm_sync', label: 'Synchronisation CRM', state: 'pending', at: null, detail: null },
      { key: 'draft_generated', label: 'Brouillon généré', state: 'pending', at: null, detail: null },
      { key: 'human_review', label: 'Revue humaine', state: 'pending', at: null, detail: null },
      { key: 'decision', label: 'Décision', state: 'pending', at: null, detail: null },
    ],
    ...overrides,
  }
}
