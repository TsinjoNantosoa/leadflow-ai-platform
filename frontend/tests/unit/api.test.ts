import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiFetch, setCsrfToken, UNAUTHORIZED_EVENT } from '@/lib/api'
import { mockApi } from './helpers'

beforeEach(() => {
  setCsrfToken(null)
  vi.unstubAllGlobals()
})

describe('apiFetch', () => {
  it('utilise la base /api, envoie les cookies et ne stocke aucun jeton dans localStorage', async () => {
    const api = mockApi([{ path: '/api/v1/leads', body: { items: [] } }])
    await apiFetch('/v1/leads')
    const init = api.fetchMock.mock.calls[0]![1] as RequestInit
    expect(api.calls[0]!.url.pathname).toBe('/api/v1/leads')
    expect(init.credentials).toBe('include')
    expect(localStorage.length).toBe(0)
  })

  it('ajoute le jeton CSRF aux mutations uniquement', async () => {
    const api = mockApi([
      { path: '/api/v1/leads', body: {} },
      { method: 'POST', path: '/api/v1/leads/1/retry', body: {} },
    ])
    setCsrfToken('tok')
    await apiFetch('/v1/leads')
    await apiFetch('/v1/leads/1/retry', { method: 'POST' })
    expect(api.calls[0]!.headers['X-CSRF-Token']).toBeUndefined()
    expect(api.calls[1]!.headers['X-CSRF-Token']).toBe('tok')
  })

  it('sérialise la requête sans les valeurs vides', async () => {
    const api = mockApi([{ path: '/api/v1/leads', body: {} }])
    await apiFetch('/v1/leads', { query: { q: 'dupont', status: '', page: 2, segment: undefined, review: false } })
    expect(api.calls[0]!.url.search).toBe('?q=dupont&page=2&review=false')
  })

  it('normalise les erreurs API avec code, message et identifiant de corrélation', async () => {
    mockApi([{ path: '/api/v1/leads', status: 403, body: { error: { code: 'forbidden', message: 'Droits insuffisants', details: { a: 1 } } } }])
    const err = (await apiFetch('/v1/leads').catch((e: unknown) => e)) as ApiError
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status: 403, code: 'forbidden', message: 'Droits insuffisants', correlationId: 'corr-test-123' })
  })

  it('émet un événement global sur 401 sauf pour les appels d’authentification silencieux', async () => {
    mockApi([{ path: '/api/v1/leads', status: 401, body: { error: { code: 'not_authenticated', message: 'x' } } }])
    const spy = vi.fn()
    window.addEventListener(UNAUTHORIZED_EVENT, spy)
    await apiFetch('/v1/leads').catch(() => undefined)
    expect(spy).toHaveBeenCalledTimes(1)
    await apiFetch('/v1/leads', { silentUnauthorized: true }).catch(() => undefined)
    expect(spy).toHaveBeenCalledTimes(1)
    window.removeEventListener(UNAUTHORIZED_EVENT, spy)
  })

  it('réessaie une lecture sur 503 (cold start) puis réussit', async () => {
    let n = 0
    const api = mockApi([{ path: '/api/v1/leads', handler: () => (++n < 3 ? { status: 503, body: { error: { code: 'service_unavailable', message: 'x' } } } : { body: { ok: true } }) }])
    await expect(apiFetch('/v1/leads', { retryBaseDelayMs: 1 })).resolves.toEqual({ ok: true })
    expect(api.calls).toHaveLength(3)
  })

  it('ne rejoue JAMAIS une mutation sans clé d’idempotence', async () => {
    const api = mockApi([{ method: 'POST', path: '/api/v1/leads/1/retry', status: 503, body: { error: { code: 'x', message: 'x' } } }])
    await apiFetch('/v1/leads/1/retry', { method: 'POST', retryBaseDelayMs: 1 }).catch(() => undefined)
    expect(api.calls).toHaveLength(1)
  })

  it('rejoue une mutation protégée par Idempotency-Key avec la MÊME clé', async () => {
    let n = 0
    const api = mockApi([{ method: 'POST', path: '/api/v1/public/leads', handler: () => (++n < 2 ? { status: 502, body: {} } : { status: 201, body: { lead_id: 'l' } }) }])
    await apiFetch('/v1/public/leads', { method: 'POST', body: { a: 1 }, idempotencyKey: 'key-1', retryBaseDelayMs: 1 })
    expect(api.calls.map((c) => c.headers['Idempotency-Key'])).toEqual(['key-1', 'key-1'])
  })

  it('traduit une coupure réseau et un timeout en ApiError status 0', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const err = (await apiFetch('/v1/leads', { retries: 0 }).catch((e: unknown) => e)) as ApiError
    expect(err).toMatchObject({ status: 0, code: 'network_error' })
    expect(err.isNetwork).toBe(true)
  })

  it('retourne undefined sur 204', async () => {
    mockApi([{ method: 'POST', path: '/api/v1/auth/logout', status: 204 }])
    await expect(apiFetch('/v1/auth/logout', { method: 'POST' })).resolves.toBeUndefined()
  })
})
