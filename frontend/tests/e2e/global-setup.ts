import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import { DB_URL, PYTHON } from '../../playwright.config'

// Base jetable recréée AVANT le démarrage du backend (globalSetup s'exécute après les webServers : le backend ne lit
// la base qu'à la première requête, donc la préparation reste valable).
export default function globalSetup() {
  execFileSync(PYTHON, ['-m', 'scripts.e2e_prepare'], {
    cwd: resolve(import.meta.dirname, '../../../backend'),
    env: { ...process.env, E2E_DATABASE_URL: DB_URL, PYTHONIOENCODING: 'utf-8' },
    stdio: 'inherit',
  })
}
