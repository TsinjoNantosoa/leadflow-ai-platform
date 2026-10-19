import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { routes } from '@/app/router'
import { meRoute, mockApi, renderRoutes, session } from './helpers'

const emptyOverview = {
  generated_at: '2026-10-19T10:00:00Z', data_origin: { total_leads: 0, demo_leads: 0, real_leads: 0 },
  leads: { received: 0, qualified: 0, manual_review: 0, failed: 0, in_progress: 0, by_status: {} },
  segments: { HOT: 0, WARM: 0, COLD: 0 }, series: [], runs_last_7_days: {}, outbox: {}, drafts: {}, crm: {},
  automation_performance: { successful_runs_7d: 0, avg_duration_ms: null, p95_duration_ms: null, retries_total: 0, dead_letter: 0 },
  qualification_latency_seconds: { samples: 0, p50: null, p95: null, scope: '' },
  llm_usage: { calls: 0, input_tokens: 0, output_tokens: 0, estimated_cost_usd: null, scope: '' }, recent_activity: [],
}

beforeEach(() => vi.unstubAllGlobals())

describe('Navigation et accès', () => {
  it.each(['/app/overview', '/app/leads', '/app/leads/abc', '/app/reviews', '/app/runs'])(
    'redirige un visiteur anonyme de %s vers /login (et ne charge aucune donnée privée)',
    async (path) => {
      const api = mockApi([meRoute(null)])
      renderRoutes(routes, [path])
      expect(await screen.findByRole('heading', { name: /connexion/i })).toBeInTheDocument()
      expect(api.calls.filter((c) => c.url.pathname !== '/api/v1/auth/me')).toHaveLength(0)
    },
  )

  it('les pages publiques restent accessibles sans session', async () => {
    mockApi([meRoute(null)])
    renderRoutes(routes, ['/'])
    expect(await screen.findByRole('heading', { level: 1, name: /qualifiez vos demandes/i })).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: /tester la démo/i }).length).toBeGreaterThan(0)
  })

  it('connexion réussie : stocke le CSRF en mémoire et redirige vers la page demandée', async () => {
    const api = mockApi([
      meRoute(null),
      { method: 'POST', path: '/api/v1/auth/login', body: session('SALES') as never },
      { path: '/api/v1/metrics/overview', body: emptyOverview as never },
    ])
    const user = userEvent.setup()
    renderRoutes(routes, ['/app/overview'])
    await screen.findByRole('heading', { name: /connexion/i })
    await user.type(screen.getByLabelText(/e-mail/i), 'sales@novadigital.example')
    await user.type(screen.getByLabelText(/mot de passe/i), 'secret-pass')
    await user.click(screen.getByRole('button', { name: /se connecter/i }))
    // 1re importation du chunk Vue d’ensemble (recharts) : lente sous charge parallèle, d’où le délai élargi
    expect(await screen.findByRole('heading', { name: /vue d’ensemble/i }, { timeout: 15000 })).toBeInTheDocument()
    expect(api.calls.find((c) => c.url.pathname === '/api/v1/auth/login')?.json).toEqual({ email: 'sales@novadigital.example', password: 'secret-pass' })
    expect(localStorage.getItem('lf-token')).toBeNull()
    expect(JSON.stringify({ ...localStorage })).not.toContain('csrf-test-token')
  })

  it('échec de connexion : message générique sans détail sur le compte', async () => {
    mockApi([meRoute(null), { method: 'POST', path: '/api/v1/auth/login', status: 401, body: { error: { code: 'invalid_credentials', message: 'Identifiants invalides' } } }])
    const user = userEvent.setup()
    renderRoutes(routes, ['/login'])
    await user.type(await screen.findByLabelText(/e-mail/i), 'x@example.org')
    await user.type(screen.getByLabelText(/mot de passe/i), 'bad')
    await user.click(screen.getByRole('button', { name: /se connecter/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/incorrect, ou compte temporairement verrouillé/i)
  })

  it('validation du formulaire de connexion', async () => {
    mockApi([meRoute(null)])
    const user = userEvent.setup()
    renderRoutes(routes, ['/login'])
    await user.click(await screen.findByRole('button', { name: /se connecter/i }))
    expect(await screen.findByText('Indiquez votre e-mail')).toBeInTheDocument()
    expect(screen.getByText('Indiquez votre mot de passe')).toBeInTheDocument()
  })

  it('une session expirée (401 en cours de navigation) renvoie vers /login', async () => {
    mockApi([
      meRoute('SALES'),
      { path: '/api/v1/metrics/overview', status: 401, body: { error: { code: 'not_authenticated', message: 'x' } } },
    ])
    renderRoutes(routes, ['/app/overview'])
    expect(await screen.findByRole('heading', { name: /connexion/i })).toBeInTheDocument()
  })

  it('un utilisateur connecté qui ouvre /login est renvoyé vers le dashboard', async () => {
    mockApi([meRoute('SALES'), { path: '/api/v1/metrics/overview', body: emptyOverview as never }])
    renderRoutes(routes, ['/login'])
    expect(await screen.findByRole('heading', { name: /vue d’ensemble/i })).toBeInTheDocument()
  })

  it('la navigation de l’application expose les 4 sections et se déconnecte côté serveur', async () => {
    const api = mockApi([
      meRoute('SALES'),
      { path: '/api/v1/metrics/overview', body: emptyOverview as never },
      { method: 'POST', path: '/api/v1/auth/logout', status: 204 },
    ])
    const user = userEvent.setup()
    renderRoutes(routes, ['/app/overview'])
    await screen.findByRole('heading', { name: /vue d’ensemble/i })
    const nav = screen.getAllByRole('navigation', { name: /navigation de l’application/i })[0]!
    for (const label of [/vue d’ensemble/i, /leads/i, /revue humaine/i, /automatisations/i]) expect(within(nav).getByRole('link', { name: label })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /menu utilisateur/i }))
    await user.click(await screen.findByRole('menuitem', { name: /se déconnecter/i }))
    await waitFor(() => expect(api.count('POST', '/api/v1/auth/logout')).toBe(1))
    expect(await screen.findByRole('heading', { name: /connexion/i })).toBeInTheDocument()
  })

  it('page inconnue : 404 propre', async () => {
    mockApi([meRoute(null)])
    renderRoutes(routes, ['/nimporte-quoi'])
    expect(await screen.findByRole('heading', { name: /page introuvable/i })).toBeInTheDocument()
  })

  it('le bandeau « données de démonstration » n’apparaît que si la base en contient', async () => {
    mockApi([meRoute('SALES'), { path: '/api/v1/metrics/overview', body: { ...emptyOverview, data_origin: { total_leads: 15, demo_leads: 15, real_leads: 0 } } as never }])
    renderRoutes(routes, ['/app/overview'])
    expect(await screen.findByText(/données de démonstration :/i)).toBeInTheDocument()
  })
})
