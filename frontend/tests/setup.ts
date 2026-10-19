import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { afterEach } from 'vitest'

configure({ asyncUtilTimeout: 5000 })
afterEach(() => cleanup())

// jsdom n'implémente pas ces API utilisées par Radix / Recharts.
class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= RO as unknown as typeof ResizeObserver
Element.prototype.scrollIntoView ??= () => {}
Element.prototype.hasPointerCapture ??= () => false
Element.prototype.releasePointerCapture ??= () => {}
window.matchMedia ??= ((q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, onchange: null, dispatchEvent: () => false })) as unknown as typeof window.matchMedia

// jsdom fournit son propre AbortSignal, que le `Request` natif de Node (undici) refuse : React Router en crée un à chaque
// navigation. On retire le signal (l'annulation de navigation n'a pas d'intérêt dans ces tests).
const NativeRequest = globalThis.Request
globalThis.Request = class extends NativeRequest {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    if (init && 'signal' in init) {
      const { signal: _ignored, ...rest } = init
      super(input, rest)
    } else {
      super(input, init)
    }
  }
} as typeof Request
