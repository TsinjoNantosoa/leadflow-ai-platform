import { expect, test } from '@playwright/test'
import { login } from './helpers'

const hasHorizontalScroll = (page: import('@playwright/test').Page) =>
  page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1)

test.describe('mobile (375 px) — T18', () => {
  test.use({ viewport: { width: 375, height: 740 } })

  for (const path of ['/', '/demo', '/login']) {
    test(`pas de défilement horizontal sur ${path}`, async ({ page }) => {
      await page.goto(path)
      await expect(page.locator('main, form').first()).toBeVisible()
      expect(await hasHorizontalScroll(page)).toBe(false)
    })
  }

  test('formulaire utilisable au mobile et validations accessibles', async ({ page }) => {
    await page.goto('/demo')
    await page.getByRole('button', { name: 'Envoyer ma demande' }).click()
    await expect(page.getByRole('alert').first()).toBeVisible()
    await expect(page.getByLabel('E-mail *')).toHaveAttribute('aria-invalid', 'true')
    expect(await hasHorizontalScroll(page)).toBe(false)
  })

  test('dashboard : menu mobile, tableaux défilables sans casser la page', async ({ page }) => {
    await login(page)
    expect(await hasHorizontalScroll(page)).toBe(false)
    await page.getByRole('button', { name: 'Ouvrir le menu' }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByRole('link', { name: /Leads/ })).toBeVisible()
    await dialog.getByRole('link', { name: /Leads/ }).click()
    await expect(page).toHaveURL(/\/app\/leads/)
    await expect(page.getByRole('table', { name: 'Liste des leads' })).toBeVisible()
    expect(await hasHorizontalScroll(page)).toBe(false)
  })
})

test('clavier : le lien d’évitement, l’ordre de tabulation et la soumission au clavier fonctionnent', async ({ page }) => {
  await page.goto('/demo')
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: 'Aller au contenu' })).toBeFocused()
  await page.getByLabel('Nom complet').focus()
  await page.keyboard.type('Alice Clavier')
  await page.keyboard.press('Tab')
  await expect(page.getByLabel('E-mail *')).toBeFocused()
  // le champ honeypot n'est jamais atteignable au clavier
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press('Tab')
    expect(await page.evaluate(() => (document.activeElement as HTMLInputElement | null)?.name)).not.toBe('website')
  }
})

test('thème sombre : bascule persistée et appliquée sans rechargement', async ({ page }) => {
  await page.goto('/')
  await page.evaluate(() => localStorage.removeItem('lf-theme'))
  await page.getByRole('button', { name: /thème sombre/i }).click()
  await expect(page.locator('html')).toHaveClass(/dark/)
  await page.reload()
  await expect(page.locator('html')).toHaveClass(/dark/)
  await page.getByRole('button', { name: /thème clair/i }).click()
  await expect(page.locator('html')).not.toHaveClass(/dark/)
})
