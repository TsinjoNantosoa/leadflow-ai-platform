import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import DemoPage from '@/pages/DemoPage'
import { SAMPLE_LEAD } from '@/features/lead-form'
import { mockApi, renderPage } from './helpers'

const receipt = { lead_id: '11111111-1111-4111-8111-111111111111', status: 'NEW', request_id: '22222222-2222-4222-8222-222222222222' }

beforeEach(() => vi.unstubAllGlobals())

async function fillSample(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByTestId('fill-sample'))
}

describe('Formulaire /demo', () => {
  it('affiche les erreurs de validation en français et n’appelle pas l’API', async () => {
    const api = mockApi([{ method: 'POST', path: '/api/v1/public/leads', status: 201, body: receipt }])
    const user = userEvent.setup()
    renderPage(<DemoPage />)
    await user.click(screen.getByRole('button', { name: /envoyer ma demande/i }))
    expect(await screen.findByText('Indiquez votre e-mail')).toBeInTheDocument()
    expect(screen.getByText(/au moins 20 caractères/)).toBeInTheDocument()
    expect(screen.getByText(/consentement est nécessaire/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/e-mail \*/i)).toHaveAttribute('aria-invalid', 'true')
    expect(api.count('POST', '/api/v1/public/leads')).toBe(0)
  })

  it('préremplit le scénario fictif facultatif', async () => {
    mockApi([])
    const user = userEvent.setup()
    renderPage(<DemoPage />)
    await fillSample(user)
    expect(screen.getByLabelText(/nom complet/i)).toHaveValue(SAMPLE_LEAD.full_name)
    expect(screen.getByLabelText(/e-mail \*/i)).toHaveValue('alice.martin@example.org')
    expect(screen.getByLabelText(/service recherché/i)).toHaveValue('customer_support_automation')
  })

  it('envoie avec une Idempotency-Key UUID et affiche la confirmation avec l’identifiant de demande', async () => {
    const api = mockApi([{ method: 'POST', path: '/api/v1/public/leads', status: 201, body: receipt }])
    const user = userEvent.setup()
    renderPage(<DemoPage />)
    await fillSample(user)
    await user.click(screen.getByRole('button', { name: /envoyer ma demande/i }))
    expect(await screen.findByRole('heading', { name: /demande bien reçue/i })).toBeInTheDocument()
    const call = api.calls.find((c) => c.method === 'POST')!
    expect(call.headers['Idempotency-Key']).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
    expect(call.json).toMatchObject({ email: 'alice.martin@example.org', consent_privacy: true, consent_marketing: false })
    expect(screen.getByTestId('request-id')).toHaveTextContent('22222222')
    expect(screen.getByText(/aucun e-mail automatique/i)).toBeInTheDocument()
  })

  it('résiste aux doubles clics : une seule requête part', async () => {
    const api = mockApi([{ method: 'POST', path: '/api/v1/public/leads', handler: () => ({ status: 201, body: receipt, delayMs: 60 }) }])
    const user = userEvent.setup()
    renderPage(<DemoPage />)
    await fillSample(user)
    const btn = screen.getByRole('button', { name: /envoyer ma demande/i })
    await user.dblClick(btn)
    await user.click(btn)
    await screen.findByRole('heading', { name: /demande bien reçue/i })
    expect(api.count('POST', '/api/v1/public/leads')).toBe(1)
  })

  it('désactive le bouton pendant l’envoi (état de soumission)', async () => {
    mockApi([{ method: 'POST', path: '/api/v1/public/leads', handler: () => ({ status: 201, body: receipt, delayMs: 80 }) }])
    const user = userEvent.setup()
    renderPage(<DemoPage />)
    await fillSample(user)
    await user.click(screen.getByRole('button', { name: /envoyer ma demande/i }))
    const busy = await screen.findByRole('button', { name: /envoi en cours/i })
    expect(busy).toBeDisabled()
    expect(busy).toHaveAttribute('aria-busy', 'true')
  })

  it('après une erreur serveur, un nouvel essai réutilise la MÊME clé (aucun doublon possible)', async () => {
    let n = 0
    const api = mockApi([
      {
        method: 'POST', path: '/api/v1/public/leads',
        handler: () => (++n === 1 ? { status: 400, body: { error: { code: 'x', message: 'Erreur de test' } } } : { status: 201, body: receipt }),
      },
    ])
    const user = userEvent.setup()
    renderPage(<DemoPage />)
    await fillSample(user)
    await user.click(screen.getByRole('button', { name: /envoyer ma demande/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/erreur de test/i)
    expect(screen.getByText(/aucune demande en double/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /envoyer ma demande/i }))
    await screen.findByRole('heading', { name: /demande bien reçue/i })
    const keys = api.calls.filter((c) => c.method === 'POST').map((c) => c.headers['Idempotency-Key'])
    expect(keys).toHaveLength(2)
    expect(keys[0]).toBe(keys[1])
  })

  it('une modification du contenu génère une NOUVELLE clé', async () => {
    let n = 0
    const api = mockApi([
      { method: 'POST', path: '/api/v1/public/leads', handler: () => (++n === 1 ? { status: 429, body: { error: { code: 'rate_limited', message: 'Trop' } } } : { status: 201, body: receipt }) },
    ])
    const user = userEvent.setup()
    renderPage(<DemoPage />)
    await fillSample(user)
    await user.click(screen.getByRole('button', { name: /envoyer ma demande/i }))
    await screen.findByRole('alert')
    await user.type(screen.getByLabelText(/votre message/i), ' Précision ajoutée.')
    await user.click(screen.getByRole('button', { name: /envoyer ma demande/i }))
    await waitFor(() => expect(api.count('POST', '/api/v1/public/leads')).toBe(2))
    const keys = api.calls.filter((c) => c.method === 'POST').map((c) => c.headers['Idempotency-Key'])
    expect(keys[0]).not.toBe(keys[1])
  })

  it('le honeypot est invisible et hors navigation clavier', () => {
    mockApi([])
    renderPage(<DemoPage />)
    const trap = document.querySelector('input[name="website"]') as HTMLInputElement
    expect(trap).toHaveAttribute('tabindex', '-1')
    expect(trap.closest('[aria-hidden="true"]')).not.toBeNull()
  })

  it('indique le message réseau explicite quand le serveur est injoignable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const user = userEvent.setup()
    renderPage(<DemoPage />)
    await fillSample(user)
    await user.click(screen.getByRole('button', { name: /envoyer ma demande/i }))
    expect(await screen.findByText(/serveur injoignable/i, undefined, { timeout: 8000 })).toBeInTheDocument()
  }, 15000)
})
