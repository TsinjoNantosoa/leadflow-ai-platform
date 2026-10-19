import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import { expect, type Page } from '@playwright/test'
import { API_PORT, PYTHON, SERVICE_TOKEN } from '../../playwright.config'

export const SALES = { email: 'sales@novadigital.example', password: process.env.E2E_SALES_PASSWORD ?? 'Sales-E2E-Pass-1!' }
export const ADMIN = { email: 'admin@novadigital.example', password: process.env.E2E_ADMIN_PASSWORD ?? 'Admin-E2E-Pass-1!' }

/** Fait tourner le worker de référence (équivalent des workflows n8n) jusqu'à épuisement de l'outbox. */
export function runWorker(): string {
  return execFileSync(
    PYTHON,
    ['-m', 'scripts.dev_worker', '--base-url', `http://localhost:${API_PORT}`, '--token', SERVICE_TOKEN, '--drain'],
    { cwd: resolve(import.meta.dirname, '../../../backend'), encoding: 'utf-8' },
  )
}

export async function login(page: Page, who = SALES) {
  await page.goto('/login')
  await page.getByLabel('E-mail').fill(who.email)
  await page.getByLabel('Mot de passe').fill(who.password)
  await page.getByRole('button', { name: 'Se connecter' }).click()
  await expect(page).toHaveURL(/\/app\/overview/)
}

export const uniqueEmail = (tag: string) => `e2e-${tag}-${Date.now()}@example.org`

export async function submitLeadViaForm(page: Page, email: string, name = 'Alice E2E') {
  await page.goto('/demo')
  await page.getByTestId('fill-sample').click()
  await page.getByLabel('Nom complet').fill(name)
  await page.getByLabel('E-mail *').fill(email)
  await page.getByRole('button', { name: 'Envoyer ma demande' }).click()
  await expect(page.getByRole('heading', { name: 'Demande bien reçue' })).toBeVisible()
}
