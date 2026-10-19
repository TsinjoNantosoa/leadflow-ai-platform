import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineConfig, devices } from '@playwright/test'

// E2E : vrai backend FastAPI + vraie base PostgreSQL jetable (…_playwright) + frontend compilé. Fournisseurs LLM/CRM en mode mock.
// Le « moteur n8n » est remplacé par le worker de référence (backend/scripts/dev_worker.py) qui exécute les mêmes appels HTTP.
const BACKEND_DIR = resolve(import.meta.dirname, '../backend')
export const PYTHON =
  process.env.E2E_BACKEND_PYTHON ??
  [resolve(BACKEND_DIR, '.venv/Scripts/python.exe'), resolve(BACKEND_DIR, '.venv/bin/python')].find(existsSync) ??
  'python'
export const API_PORT = Number(process.env.E2E_API_PORT ?? 8011)
export const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 4173)
export const DB_URL =
  process.env.E2E_DATABASE_URL ?? 'postgresql+psycopg://leadflow:leadflow_local@localhost:5433/leadflow_playwright'
export const SERVICE_TOKEN = 'e2e-service-token-0123456789abcdef-0123456789'

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  globalSetup: './tests/e2e/global-setup.ts',
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    locale: 'fr-FR',
    timezoneId: 'Europe/Paris',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `"${PYTHON}" -m uvicorn app.main:app --port ${API_PORT}`,
      cwd: BACKEND_DIR,
      url: `http://localhost:${API_PORT}/health`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        DATABASE_URL: DB_URL,
        APP_ENV: 'development',
        FRONTEND_URL: `http://localhost:${WEB_PORT}`,
        SESSION_SECRET: 'e2e-session-secret-0123456789abcdef0123456789',
        API_SERVICE_TOKEN: SERVICE_TOKEN,
        LLM_PROVIDER: 'mock',
        CRM_PROVIDER: 'mock',
        PUBLIC_RATE_LIMIT_PER_HOUR: '500',
        LOG_LEVEL: 'WARNING',
      },
    },
    {
      command: `npm run build && npx vite preview --port ${WEB_PORT} --strictPort`,
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 180_000,
      env: { DEV_API_PROXY_TARGET: `http://localhost:${API_PORT}` },
    },
  ],
})
