// Configure l'origine de l'API pour le rewrite Vercel (même origine => cookie de session first-party).
//   npm run configure:vercel -- https://mon-api.onrender.com   # écrit l'origine dans vercel.json (à committer)
//   npm run check:vercel                                       # échoue si l'origine est encore un placeholder
// `check:vercel` s'exécute avant le build UNIQUEMENT sur Vercel (variable VERCEL=1) : aucun déploiement ne peut
// partir avec une URL factice. L'origine n'est pas un secret (c'est l'URL publique de l'API).
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const PLACEHOLDER = '__RENDER_API_ORIGIN__'

export function validateOrigin(raw) {
  let u
  try {
    u = new URL(raw)
  } catch {
    throw new Error(`URL invalide : ${raw}`)
  }
  if (u.protocol !== 'https:') throw new Error('L’origine de l’API doit être en https://')
  if (u.pathname !== '/' || u.search || u.hash || u.username) throw new Error('Fournir seulement l’origine (https://hôte), sans chemin')
  if (/example\.|your-|localhost|127\.0\.0\.1/i.test(u.hostname)) throw new Error('Origine factice ou locale refusée')
  return u.origin
}

export function applyOrigin(json, origin) {
  return json.replaceAll(PLACEHOLDER, origin).replace(/https:\/\/[^"/]+(?=\/api\/:path\*)/, origin)
}

export function hasPlaceholder(json) {
  return json.includes(PLACEHOLDER)
}

const mode = process.argv[2]
if (typeof process !== 'undefined' && /vercel-config\.mjs$/.test(process.argv[1] ?? '')) {
  try {
    const FILE = fileURLToPath(new URL('../vercel.json', import.meta.url))
    const text = readFileSync(FILE, 'utf8')
    if (mode === '--check') {
      if (process.env.VERCEL && hasPlaceholder(text)) {
        console.error('[vercel] vercel.json contient encore l’origine factice. Lancez : npm run configure:vercel -- https://<service>.onrender.com')
        process.exit(1)
      }
    } else if (mode) {
      writeFileSync(FILE, applyOrigin(text, validateOrigin(mode)))
      console.log(`[vercel] origine API configurée : ${validateOrigin(mode)}`)
    } else {
      console.error('usage : npm run configure:vercel -- https://<service>.onrender.com')
      process.exit(2)
    }
  } catch (e) {
    console.error(`[vercel] ${e.message}`)
    process.exit(2)
  }
}
