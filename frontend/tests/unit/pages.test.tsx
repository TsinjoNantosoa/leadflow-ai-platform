import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LeadTimeline } from '@/components/domain/timeline'
import { ScoreBreakdown } from '@/components/domain/score'
import { routes } from '@/app/router'
import { leadDetail, meRoute, mockApi, renderRoutes } from './helpers'
import type { Followup, FollowupReviewItem, Run } from '@/types/api'

beforeEach(() => vi.unstubAllGlobals())

const listItem = (over: Record<string, unknown> = {}) => ({
  id: 'lead-1', created_at: '2026-10-19T09:00:00Z', status: 'READY', status_reason: null, full_name: 'Alice Martin', email: 'alice@example.org',
  company: 'Acme', requested_service: 'customer_support_automation', service: 'customer_support_automation', score: 100, segment: 'HOT',
  human_review_required: false, crm_status: 'SYNCED', followup_status: 'DRAFT', is_demo: false, ...over,
})
const page = <T,>(items: T[], total = items.length) => ({ items, total, page: 1, page_size: 20 })

describe('Leads', () => {
  it('liste, état de chargement puis tableau avec score, segment et statut', async () => {
    mockApi([meRoute('SALES'), { path: '/api/v1/leads', body: page([listItem(), listItem({ id: 'l2', full_name: 'Bob Roux', score: null, segment: null, status: 'NEW', crm_status: null, followup_status: null })]) as never }])
    renderRoutes(routes, ['/app/leads'])
    expect(await screen.findByRole('link', { name: /alice martin/i })).toHaveAttribute('href', '/app/leads/lead-1')
    const table = within(await screen.findByRole('table', { name: /liste des leads/i }))
    expect(table.getByText('HOT')).toBeInTheDocument()
    expect(screen.getByText('Non qualifié')).toBeInTheDocument()
    expect(table.getByText('Prêt')).toBeInTheDocument()
  })

  it('envoie les filtres au serveur (recherche, statut, segment) et les reflète dans l’URL', async () => {
    const api = mockApi([meRoute('SALES'), { path: '/api/v1/leads', body: page([listItem()]) as never }])
    const user = userEvent.setup()
    const { router } = renderRoutes(routes, ['/app/leads'])
    await screen.findByRole('link', { name: /alice martin/i })
    await user.selectOptions(screen.getByLabelText(/filtrer par segment/i), 'HOT')
    await user.selectOptions(screen.getByLabelText(/filtrer par statut/i), 'MANUAL_REVIEW')
    await user.type(screen.getByLabelText(/rechercher un lead/i), 'dupont')
    await waitFor(() => {
      const last = api.calls.filter((c) => c.url.pathname === '/api/v1/leads').at(-1)!
      expect(last.url.searchParams.get('segment')).toBe('HOT')
      expect(last.url.searchParams.get('status')).toBe('MANUAL_REVIEW')
      expect(last.url.searchParams.get('q')).toBe('dupont')
    })
    expect(router.state.location.search).toContain('segment=HOT')
  })

  it('pagination : demande la page suivante', async () => {
    const api = mockApi([meRoute('SALES'), { path: '/api/v1/leads', handler: ({ url }) => ({ body: { items: [listItem()], total: 45, page: Number(url.searchParams.get('page') ?? 1), page_size: 20 } as never }) }])
    const user = userEvent.setup()
    renderRoutes(routes, ['/app/leads'])
    await screen.findByRole('link', { name: /alice martin/i })
    expect(screen.getByText('1–20 sur 45')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /page suivante/i }))
    await waitFor(() => expect(api.calls.some((c) => c.url.searchParams.get('page') === '2')).toBe(true))
  })

  it('état vide avec filtres puis réinitialisation', async () => {
    mockApi([meRoute('SALES'), { path: '/api/v1/leads', body: page([]) as never }])
    renderRoutes(routes, ['/app/leads?segment=COLD'])
    expect(await screen.findByText(/aucun lead ne correspond/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /réinitialiser/i })).toBeInTheDocument()
  })

  it('état d’erreur avec référence de corrélation et bouton Réessayer', async () => {
    let fail = true
    mockApi([meRoute('SALES'), { path: '/api/v1/leads', handler: () => (fail ? { status: 500, body: { error: { code: 'internal_error', message: 'Erreur interne' } } } : { body: page([listItem()]) as never }) }])
    const user = userEvent.setup()
    renderRoutes(routes, ['/app/leads'])
    expect(await screen.findByRole('alert')).toHaveTextContent(/référence : corr-test-123/i)
    fail = false
    await user.click(screen.getByRole('button', { name: /réessayer/i }))
    expect(await screen.findByRole('link', { name: /alice martin/i })).toBeInTheDocument()
  })
})

describe('Détail d’un lead', () => {
  it('affiche demande, extraction, score et parcours ; le message du prospect est rendu en texte brut (pas de HTML)', async () => {
    mockApi([meRoute('SALES'), { path: '/api/v1/leads/lead-1', body: leadDetail() as never }])
    renderRoutes(routes, ['/app/leads/lead-1'])
    expect(await screen.findByRole('heading', { name: 'Alice Martin' })).toBeInTheDocument()
    const quote = screen.getByText(/<script>alert\(1\)<\/script>/)
    expect(quote.tagName).toBe('BLOCKQUOTE')
    expect(document.querySelector('blockquote script')).toBeNull()
    expect(screen.getByText('Automatisation du support client', { selector: 'p' })).toBeInTheDocument()
    expect(screen.getByText(/3 000/)).toBeInTheDocument()
    expect(screen.getByText('30 jours')).toBeInTheDocument()
    expect(screen.getByRole('list', { name: /parcours du lead/i })).toBeInTheDocument()
  })

  it('lead introuvable : message clair', async () => {
    mockApi([meRoute('SALES'), { path: '/api/v1/leads/zzz', status: 404, body: { error: { code: 'lead_not_found', message: 'Lead introuvable' } } }])
    renderRoutes(routes, ['/app/leads/zzz'])
    expect(await screen.findByText('Lead introuvable')).toBeInTheDocument()
  })

  it('relance du traitement : POST /retry puis rafraîchissement ; jamais pendant PROCESSING', async () => {
    const api = mockApi([
      meRoute('SALES'),
      { path: '/api/v1/leads/lead-1', body: leadDetail({ status: 'FAILED', status_reason: 'LLM_UNAVAILABLE' }) as never },
      { method: 'POST', path: '/api/v1/leads/lead-1/retry', status: 202, body: { lead_id: 'lead-1', event_id: 'e', status: 'queued' } },
    ])
    const user = userEvent.setup()
    renderRoutes(routes, ['/app/leads/lead-1'])
    await screen.findByText(/le traitement automatique a échoué/i)
    await user.click(screen.getByRole('button', { name: /relancer le traitement/i }))
    await waitFor(() => expect(api.count('POST', '/api/v1/leads/lead-1/retry')).toBe(1))
    expect(api.calls.find((c) => c.method === 'POST')!.headers['X-CSRF-Token']).toBe('csrf-test-token') // jeton de la session, en mémoire
  })

  it('bouton Relancer désactivé tant que le lead est en traitement', async () => {
    mockApi([meRoute('SALES'), { path: '/api/v1/leads/lead-1', body: leadDetail({ status: 'PROCESSING' }) as never }])
    renderRoutes(routes, ['/app/leads/lead-1'])
    await screen.findByRole('heading', { name: 'Alice Martin' })
    expect(screen.getByRole('button', { name: /relancer le traitement/i })).toBeDisabled()
  })

  it('affiche les raisons de revue humaine', async () => {
    const d = leadDetail({ status: 'MANUAL_REVIEW' })
    d.qualification!.human_review_required = true
    d.qualification!.review_reasons = ['prompt_injection_suspected']
    mockApi([meRoute('SALES'), { path: '/api/v1/leads/lead-1', body: d as never }])
    renderRoutes(routes, ['/app/leads/lead-1'])
    expect(await screen.findByText(/tentative d'instruction détectée/i)).toBeInTheDocument()
  })
})

describe('Timeline et score (composants)', () => {
  it('chaque étape expose son état à la technologie d’assistance et une étape « à venir » n’est pas présentée comme réussie', () => {
    render(<LeadTimeline steps={leadDetail().timeline} />)
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(8)
    expect(items.map((i) => i.getAttribute('data-state'))).toEqual(['done', 'done', 'done', 'done', 'pending', 'pending', 'pending', 'pending'])
    expect(within(items[4]!).getAllByText(/à venir/i).length).toBeGreaterThan(0)
  })

  it('affiche les états attention / échec / non réalisé', () => {
    render(<LeadTimeline steps={[
      { key: 'a', label: 'A', state: 'attention', at: null, detail: 'Action humaine requise' },
      { key: 'b', label: 'B', state: 'failed', at: null, detail: 'HTTP_401' },
      { key: 'c', label: 'C', state: 'skipped', at: null, detail: 'prompt_injection_suspected' },
    ]} />)
    expect(screen.getByText('Action humaine requise')).toBeInTheDocument()
    expect(screen.getByText('HTTP_401')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem').map((i) => i.getAttribute('data-state'))).toEqual(['attention', 'failed', 'skipped'])
  })

  it('le score explicable détaille chaque facteur (points / plafond / justification)', () => {
    render(<ScoreBreakdown qualification={leadDetail().qualification!} />)
    expect(screen.getByRole('img', { name: /score 100 sur 100, segment hot/i })).toBeInTheDocument()
    expect(screen.getByText('aucun budget mentionné')).toBeInTheDocument()
    expect(screen.getByText(/jamais par le modèle ia/i)).toBeInTheDocument()
  })
})

const followup = (over: Partial<FollowupReviewItem> = {}): FollowupReviewItem => ({
  id: 'f1', lead_id: 'lead-1', channel: 'email', subject: 'Votre demande', body: 'Bonjour Alice, merci pour votre message et votre confiance.', language: 'fr', status: 'DRAFT',
  edit_version: 1, model_name: 'mock', prompt_version: 'v1', llm_provider: 'mock', edited_by: null, edited_at: null, approved_by: null, approved_at: null,
  rejected_by: null, rejected_at: null, reject_reason: null, created_at: '2026-10-19T09:00:00Z', updated_at: '2026-10-19T09:00:00Z', is_demo: false,
  lead_full_name: 'Alice Martin', lead_company: 'Acme', lead_score: 100, lead_segment: 'HOT', ...over,
})

describe('Centre de revue humaine', () => {
  it('rappelle explicitement que l’approbation n’envoie aucun e-mail', async () => {
    mockApi([meRoute('SALES'), { path: '/api/v1/followups', body: page([followup()]) as never }])
    renderRoutes(routes, ['/app/reviews'])
    expect(await screen.findByText(/approuver ne déclenche aucun envoi/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /envoyer/i })).toBeNull()
  })

  it('approuve avec la version attendue (concurrence optimiste)', async () => {
    const api = mockApi([
      meRoute('SALES'),
      { path: '/api/v1/followups', body: page([followup({ edit_version: 3 })]) as never },
      { method: 'POST', path: '/api/v1/followups/f1/approve', body: followup({ status: 'APPROVED' }) as never },
    ])
    const user = userEvent.setup()
    renderRoutes(routes, ['/app/reviews'])
    await user.click(await screen.findByRole('button', { name: /approuver/i }))
    await waitFor(() => expect(api.count('POST', '/api/v1/followups/f1/approve')).toBe(1))
    expect(api.calls.find((c) => c.url.pathname.endsWith('/approve'))!.json).toEqual({ expected_version: 3 })
  })

  it('modifie le texte puis enregistre (PATCH avec expected_version)', async () => {
    const api = mockApi([
      meRoute('SALES'),
      { path: '/api/v1/followups', body: page([followup()]) as never },
      { method: 'PATCH', path: '/api/v1/followups/f1', body: followup({ edit_version: 2 }) as never },
    ])
    const user = userEvent.setup()
    renderRoutes(routes, ['/app/reviews'])
    await user.click(await screen.findByRole('button', { name: /modifier/i }))
    const body = screen.getByLabelText('Message')
    await user.clear(body)
    await user.type(body, 'Bonjour Alice, texte corrigé par le commercial après relecture attentive.')
    await user.click(screen.getByRole('button', { name: /enregistrer/i }))
    await waitFor(() => expect(api.count('PATCH', '/api/v1/followups/f1')).toBe(1))
    expect(api.calls.find((c) => c.method === 'PATCH')!.json).toMatchObject({ expected_version: 1, body: expect.stringContaining('corrigé') })
  })

  it('rejette avec une raison via une boîte de dialogue de confirmation', async () => {
    const api = mockApi([
      meRoute('SALES'),
      { path: '/api/v1/followups', body: page([followup()]) as never },
      { method: 'POST', path: '/api/v1/followups/f1/reject', body: followup({ status: 'REJECTED' }) as never },
    ])
    const user = userEvent.setup()
    renderRoutes(routes, ['/app/reviews'])
    await user.click(await screen.findByRole('button', { name: /^rejeter$/i }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText(/raison/i), 'Ton trop familier')
    await user.click(within(dialog).getByRole('button', { name: /confirmer le rejet/i }))
    await waitFor(() => expect(api.count('POST', '/api/v1/followups/f1/reject')).toBe(1))
    expect(api.calls.find((c) => c.url.pathname.endsWith('/reject'))!.json).toEqual({ reason: 'Ton trop familier' })
  })

  it('un brouillon approuvé n’offre plus d’actions et précise qu’aucun e-mail n’a été envoyé', async () => {
    mockApi([meRoute('SALES'), { path: '/api/v1/followups', body: page([followup({ status: 'APPROVED', approved_by: 'sales@novadigital.example', approved_at: '2026-10-19T10:00:00Z' })]) as never }])
    renderRoutes(routes, ['/app/reviews'])
    expect(await screen.findByText(/aucun e-mail n’a été envoyé\./i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /approuver|modifier|^rejeter$/i })).toBeNull()
  })

  it('affiche l’historique des décisions', async () => {
    mockApi([
      meRoute('SALES'),
      { path: '/api/v1/followups', body: page([followup({ status: 'APPROVED', approved_by: 'x', approved_at: '2026-10-19T10:00:00Z' })]) as never },
      { path: '/api/v1/followups/f1/history', body: [{ id: 'h1', action: 'draft.approved', actor_type: 'user', actor_ref: 'sales@novadigital.example', metadata: {}, created_at: '2026-10-19T10:00:00Z' }] as never },
    ])
    const user = userEvent.setup()
    renderRoutes(routes, ['/app/reviews'])
    await user.click(await screen.findByRole('button', { name: /historique/i }))
    expect(await screen.findByRole('list', { name: /historique des décisions/i })).toHaveTextContent('Brouillon approuvé')
  })

  it('état vide', async () => {
    mockApi([meRoute('SALES'), { path: '/api/v1/followups', body: page([]) as never }])
    renderRoutes(routes, ['/app/reviews'])
    expect(await screen.findByText(/aucun brouillon à examiner/i)).toBeInTheDocument()
  })
})

const run = (over: Partial<Run> = {}): Run => ({
  id: 'r1', lead_id: 'lead-1', outbox_event_id: 'e1', correlation_id: '9e8d7c6b-1111-4222-8333-444455556666', workflow_name: 'LF-WF-02-HubSpot-CRM-Sync', event_type: 'CRM_SYNC_REQUESTED',
  status: 'FAILED', attempt_count: 5, max_attempts: 5, error_code: 'HUBSPOT_AUTH_401', error_message: null, duration_ms: 2400, started_at: '2026-10-19T09:00:00Z', finished_at: null,
  event_status: 'DEAD_LETTER', next_attempt_at: null, can_retry: true, is_demo: false, ...over,
})

describe('Monitor d’automatisation', () => {
  it('affiche workflow, statut, tentatives, durée, code d’erreur et corrélation', async () => {
    mockApi([meRoute('ADMIN'), { path: '/api/v1/automation-runs', body: page([run()]) as never }])
    renderRoutes(routes, ['/app/runs'])
    expect(await screen.findByText('HUBSPOT_AUTH_401')).toBeInTheDocument()
    const table = within(screen.getByRole('table', { name: /exécutions/i }))
    expect(table.getByText('Synchronisation CRM')).toBeInTheDocument()
    expect(screen.getByText('5 / 5')).toBeInTheDocument()
    expect(screen.getByText('2.4 s')).toBeInTheDocument()
    expect(screen.getByText('Dead-letter')).toBeInTheDocument()
    expect(screen.getByTitle('9e8d7c6b-1111-4222-8333-444455556666')).toBeInTheDocument()
  })

  it('reprise manuelle proposée à un administrateur', async () => {
    const api = mockApi([
      meRoute('ADMIN'),
      { path: '/api/v1/automation-runs', body: page([run()]) as never },
      { method: 'POST', path: '/api/v1/automation-runs/r1/retry', status: 202, body: { event_id: 'e1', status: 'PENDING' } },
    ])
    const user = userEvent.setup()
    renderRoutes(routes, ['/app/runs'])
    await user.click(await screen.findByRole('button', { name: /reprise manuelle/i }))
    await waitFor(() => expect(api.count('POST', '/api/v1/automation-runs/r1/retry')).toBe(1))
  })

  it('permissions UI : un commercial ne voit pas le bouton de reprise (le backend refuse de toute façon)', async () => {
    mockApi([meRoute('SALES'), { path: '/api/v1/automation-runs', body: page([run()]) as never }])
    renderRoutes(routes, ['/app/runs'])
    await screen.findByText('HUBSPOT_AUTH_401')
    expect(screen.queryByRole('button', { name: /reprise manuelle/i })).toBeNull()
    expect(screen.getByText(/admin requis/i)).toBeInTheDocument()
  })

  it('une erreur 403 du serveur est présentée clairement', async () => {
    const api = mockApi([
      meRoute('ADMIN'),
      { path: '/api/v1/automation-runs', body: page([run()]) as never },
      { method: 'POST', path: '/api/v1/automation-runs/r1/retry', status: 403, body: { error: { code: 'forbidden', message: 'Droits insuffisants' } } },
    ])
    const user = userEvent.setup()
    renderRoutes(routes, ['/app/runs'])
    await user.click(await screen.findByRole('button', { name: /reprise manuelle/i }))
    await waitFor(() => expect(api.count('POST', '/api/v1/automation-runs/r1/retry')).toBe(1))
    expect(await screen.findByText(/accès refusé/i)).toBeInTheDocument()
  })

  it('filtre par statut côté serveur', async () => {
    const api = mockApi([meRoute('ADMIN'), { path: '/api/v1/automation-runs', body: page([run()]) as never }])
    const user = userEvent.setup()
    renderRoutes(routes, ['/app/runs'])
    await screen.findByText('HUBSPOT_AUTH_401')
    await user.selectOptions(screen.getByLabelText(/filtrer par statut/i), 'FAILED')
    await waitFor(() => expect(api.calls.some((c) => c.url.searchParams.get('status') === 'FAILED')).toBe(true))
  })
})

describe('Types partagés', () => {
  it('un Followup est bien un sous-ensemble du FollowupReviewItem', () => {
    const f: Followup = followup()
    expect(f.status).toBe('DRAFT')
  })
})
