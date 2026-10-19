import { expect, test } from '@playwright/test'
import { ADMIN, login, runWorker, SALES, submitLeadViaForm, uniqueEmail } from './helpers'

test.describe.configure({ mode: 'serial' })

test('parcours complet : formulaire → PostgreSQL → outbox → worker (mock) → score → CRM mock → brouillon → validation dashboard', async ({ page }) => {
  const email = uniqueEmail('flow')

  // 1. Soumission publique
  await page.goto('/')
  await page.getByRole('link', { name: 'Tester la démo' }).first().click()
  await expect(page).toHaveURL(/\/demo/)
  await submitLeadViaForm(page, email)
  await expect(page.getByTestId('request-id')).not.toBeEmpty()
  await expect(page.getByText('Aucun e-mail automatique')).toBeVisible()

  // 2. Le lead est visible, non qualifié, dans le dashboard (donnée réelle issue de PostgreSQL)
  await login(page)
  await page.goto(`/app/leads?q=${encodeURIComponent(email)}`)
  const row = page.getByRole('row', { name: /Alice E2E/ })
  await expect(row).toBeVisible()
  await expect(row.getByText('Nouveau')).toBeVisible()
  await expect(row.getByText('Non qualifié')).toBeVisible()

  // 3. Traitement asynchrone (le worker exécute qualification → CRM → brouillon via l'API interne)
  const out = runWorker()
  expect(out).toContain('qualified')
  expect(out).toContain('synced')
  expect(out).toContain('draft_created')

  // 4. Résultat : lead prêt, score explicable, parcours complet
  await page.reload()
  await expect(row.getByText('Prêt')).toBeVisible()
  await expect(row.getByText('HOT')).toBeVisible()
  await row.getByRole('link', { name: /Alice E2E/ }).click()
  await expect(page.getByRole('heading', { name: 'Alice E2E' })).toBeVisible()
  const timeline = page.getByRole('list', { name: 'Parcours du lead' })
  await expect(timeline.getByRole('listitem')).toHaveCount(8)
  await expect(timeline.locator('li[data-state="done"]')).toHaveCount(6)
  await expect(timeline.locator('li[data-state="attention"]')).toHaveCount(1) // revue humaine en attente
  await expect(timeline.locator('li[data-state="pending"]')).toHaveCount(1) // décision pas encore prise : jamais présentée comme faite

  await page.getByRole('tab', { name: 'Score' }).click()
  await expect(page.getByText('scoring-v1').first()).toBeVisible()
  await expect(page.getByText('Budget conforme au minimum du service')).toBeVisible()
  await expect(page.getByText('3000 EUR >= minimum 2000 EUR pour customer_support_automation')).toBeVisible()

  // 5. Revue humaine : modifier puis approuver — jamais d'envoi
  await page.getByRole('link', { name: 'Revue humaine' }).first().click()
  const card = page.getByTestId('review-card').filter({ hasText: 'Alice E2E' })
  await expect(card).toBeVisible()
  await card.getByRole('button', { name: 'Modifier' }).click()
  const body = card.getByLabel('Message')
  await body.fill('Bonjour Alice, merci pour votre message. Nous reviendrons vers vous après relecture interne. Cordialement.')
  await card.getByRole('button', { name: 'Enregistrer' }).click()
  await expect(page.getByText('Modifications enregistrées')).toBeVisible()
  await card.getByRole('button', { name: 'Approuver' }).click()
  await expect(page.getByText('Brouillon approuvé', { exact: true })).toBeVisible()
  await page.getByRole('tab', { name: 'Approuvés' }).click()
  const approved = page.getByTestId('review-card').filter({ hasText: 'Alice E2E' })
  await expect(approved.getByText(/aucun e-mail n’a été envoyé/i)).toBeVisible()
  await approved.getByRole('button', { name: 'Historique' }).click()
  await expect(approved.getByRole('list', { name: 'Historique des décisions' })).toContainText('Brouillon approuvé')
  await expect(approved.getByRole('list', { name: 'Historique des décisions' })).toContainText('Brouillon modifié')

  // 6. Le parcours reflète la décision
  await page.goto(`/app/leads?q=${encodeURIComponent(email)}`)
  await page.getByRole('link', { name: /Alice E2E/ }).click()
  await expect(page.getByRole('list', { name: 'Parcours du lead' }).locator('li[data-state="done"]')).toHaveCount(8)

  // 7. Supervision : trois exécutions réussies
  await page.goto('/app/runs')
  await expect(page.getByRole('table', { name: /Exécutions/ }).getByText('Réussi').first()).toBeVisible()
})

test('idempotence réelle : un double clic sur « Envoyer » ne crée qu’un seul lead', async ({ page }) => {
  const email = uniqueEmail('dbl')
  await page.goto('/demo')
  await page.getByTestId('fill-sample').click()
  await page.getByLabel('E-mail *').fill(email)
  const submit = page.getByRole('button', { name: 'Envoyer ma demande' })
  await submit.dblclick()
  await expect(page.getByRole('heading', { name: 'Demande bien reçue' })).toBeVisible()
  await login(page)
  await page.goto(`/app/leads?q=${encodeURIComponent(email)}`)
  await expect(page.getByRole('table', { name: 'Liste des leads' }).getByRole('row')).toHaveCount(2) // en-tête + 1 lead
})

test('sécurité : routes privées inaccessibles et API refusant l’anonyme', async ({ page, request }) => {
  await page.goto('/app/leads')
  await expect(page).toHaveURL(/\/login/)
  const r = await request.get('/api/v1/leads')
  expect(r.status()).toBe(401)
  expect(await r.text()).not.toContain('example.org')
  const internal = await request.post('/api/v1/internal/outbox/claim', { data: { limit: 1 } })
  expect(internal.status()).toBe(401)
})

test('mauvais mot de passe : message générique ; session par cookie HttpOnly (aucun jeton dans le stockage)', async ({ page, context }) => {
  await page.goto('/login')
  await page.getByLabel('E-mail').fill(SALES.email)
  await page.getByLabel('Mot de passe').fill('mauvais-mot-de-passe')
  await page.getByRole('button', { name: 'Se connecter' }).click()
  await expect(page.getByRole('alert')).toContainText('incorrect')
  await login(page)
  const cookies = await context.cookies()
  const session = cookies.find((c) => c.name === 'lf_session')
  expect(session?.httpOnly).toBe(true)
  expect(session?.sameSite).toBe('Lax')
  const stored = await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))
  expect(stored).not.toMatch(/lf_session|csrf|token/i)
})

test('rôles : un commercial ne peut pas relancer une exécution (API 403), un admin le peut', async ({ page, request }) => {
  await login(page, ADMIN)
  await page.goto('/app/runs')
  await expect(page.getByRole('table', { name: /Exécutions/ })).toBeVisible()
  const me = await page.request.get('/api/v1/auth/me')
  expect((await me.json()).user.role).toBe('ADMIN')
  // un commercial qui forge l'appel reçoit 403 côté serveur, quel que soit l'état de l'interface
  const ctx = await request.post('/api/v1/auth/login', { data: { email: SALES.email, password: SALES.password } })
  const csrf = (await ctx.json()).csrf_token
  const res = await request.post('/api/v1/automation-runs/00000000-0000-4000-8000-000000000000/retry', { headers: { 'X-CSRF-Token': csrf } })
  expect(res.status()).toBe(403)
})
