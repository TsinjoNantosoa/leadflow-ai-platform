import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect, test } from '@playwright/test'
import { login } from './helpers'

// Captures de documentation (données de DÉMONSTRATION synthétiques). Exécution : E2E_SCREENSHOTS=1 npx playwright test screenshots
const OUT = resolve(import.meta.dirname, '../../../docs/screenshots')
test.skip(!process.env.E2E_SCREENSHOTS, 'captures désactivées par défaut (E2E_SCREENSHOTS=1)')
test.use({ viewport: { width: 1360, height: 860 } })

async function shot(page: import('@playwright/test').Page, name: string) {
  mkdirSync(OUT, { recursive: true })
  await page.waitForLoadState('networkidle')
  await page.screenshot({ path: resolve(OUT, `${name}.png`), fullPage: false })
}

test('captures claires et sombres', async ({ page }) => {
  await page.goto('/')
  await shot(page, '01-landing')
  await page.goto('/demo')
  await page.getByTestId('fill-sample').click()
  await shot(page, '02-demo-form')
  await login(page)
  await expect(page.getByRole('heading', { name: 'Vue d’ensemble' })).toBeVisible()
  await expect(page.getByTestId('kpi-Leads reçus')).not.toHaveText('0')
  await shot(page, '03-overview')
  await page.goto('/app/leads')
  await expect(page.getByRole('table', { name: 'Liste des leads' })).toBeVisible()
  await shot(page, '04-leads')
  await page.getByRole('link', { name: /Alice Martin/ }).first().click()
  await expect(page.getByRole('list', { name: 'Parcours du lead' })).toBeVisible()
  await shot(page, '05-lead-detail')
  await page.goto('/app/reviews')
  await expect(page.getByTestId('review-card').first()).toBeVisible()
  await shot(page, '06-reviews')
  await page.goto('/app/runs')
  await expect(page.getByRole('table', { name: /Exécutions/ })).toBeVisible()
  await shot(page, '07-runs')

  await page.getByRole('button', { name: /thème sombre/i }).click()
  await page.goto('/app/overview')
  await expect(page.getByRole('heading', { name: 'Vue d’ensemble' })).toBeVisible()
  await shot(page, '08-overview-dark')
})
