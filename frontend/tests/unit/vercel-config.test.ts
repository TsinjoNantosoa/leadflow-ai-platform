import { describe, expect, it } from 'vitest'
// @ts-expect-error module .mjs sans types
import { applyOrigin, hasPlaceholder, validateOrigin } from '../../scripts/vercel-config.mjs'

describe('configuration du rewrite Vercel', () => {
  it('accepte une origine https propre', () => {
    expect(validateOrigin('https://leadflow-api.onrender.com')).toBe('https://leadflow-api.onrender.com')
  })
  it.each(['http://api.onrender.com', 'https://api.onrender.com/api', 'https://YOUR-RENDER.onrender.com', 'https://localhost', 'pas une url'])(
    'refuse %s',
    (bad) => expect(() => validateOrigin(bad)).toThrow(),
  )
  it('remplace le placeholder, détecte sa présence, et est ré-exécutable', () => {
    const src = '{"destination":"__RENDER_API_ORIGIN__/api/:path*"}'
    expect(hasPlaceholder(src)).toBe(true)
    const once = applyOrigin(src, 'https://a.onrender.com')
    expect(once).toContain('https://a.onrender.com/api/:path*')
    expect(hasPlaceholder(once)).toBe(false)
    expect(applyOrigin(once, 'https://b.onrender.com')).toContain('https://b.onrender.com/api/:path*')
  })
})
