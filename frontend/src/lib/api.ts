/**
 * Client HTTP unique. Principes :
 *  - base URL configurable (VITE_API_BASE_URL, par défaut `/api` => proxy Vite en dev, rewrite Vercel en prod) ;
 *  - session par cookie HttpOnly (jamais de jeton dans localStorage) + en-tête CSRF gardé en mémoire ;
 *  - tolérance au « cold start » de Render Free : délai long et reprises limitées sur erreurs réseau / 502-504 ;
 *  - erreurs normalisées (ApiError) incluant l'identifiant de corrélation pour le support.
 */

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>
  readonly correlationId: string | null

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}, correlationId: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
    this.correlationId = correlationId
  }

  get isNetwork() {
    return this.status === 0
  }
}

export const API_BASE: string = ((import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/api').replace(/\/+$/, '')

let csrfToken: string | null = null
export const setCsrfToken = (token: string | null) => {
  csrfToken = token
}
export const getCsrfToken = () => csrfToken

export const UNAUTHORIZED_EVENT = 'lf:unauthorized'

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
  query?: Record<string, string | number | boolean | null | undefined>
  idempotencyKey?: string
  signal?: AbortSignal
  timeoutMs?: number
  retries?: number
  retryBaseDelayMs?: number
  /** Les 401 de /auth/* ne déclenchent pas la déconnexion globale. */
  silentUnauthorized?: boolean
}

const RETRYABLE_STATUS = new Set([502, 503, 504])
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

function buildUrl(path: string, query?: RequestOptions['query']) {
  const url = `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
  if (!query) return url
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === '') continue
    params.set(k, String(v))
  }
  const qs = params.toString()
  return qs ? `${url}?${qs}` : url
}

export async function apiFetch<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const method = opts.method ?? 'GET'
  // Une requête n'est rejouée automatiquement que si elle est sûre : lecture, ou écriture protégée par Idempotency-Key.
  const replayable = method === 'GET' || Boolean(opts.idempotencyKey)
  const maxRetries = replayable ? (opts.retries ?? 2) : 0
  const baseDelay = opts.retryBaseDelayMs ?? 800

  const headers: Record<string, string> = { Accept: 'application/json' }
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json'
  if (method !== 'GET' && csrfToken) headers['X-CSRF-Token'] = csrfToken
  if (opts.idempotencyKey) headers['Idempotency-Key'] = opts.idempotencyKey

  let lastError: ApiError | null = null
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    if (attempt > 0) await sleep(baseDelay * 2 ** (attempt - 1))
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort('timeout'), opts.timeoutMs ?? 60_000)
    const onAbort = () => controller.abort(opts.signal?.reason)
    opts.signal?.addEventListener('abort', onAbort, { once: true })
    try {
      const res = await fetch(buildUrl(path, opts.query), {
        method,
        headers,
        credentials: 'include',
        body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
        signal: controller.signal,
      })
      const correlationId = res.headers.get('X-Correlation-ID')
      if (res.ok) {
        if (res.status === 204) return undefined as T
        return (await res.json()) as T
      }
      let payload: { error?: { code?: string; message?: string; details?: Record<string, unknown> } } = {}
      try {
        payload = await res.json()
      } catch {
        /* corps non JSON (ex. page d'erreur d'un proxy) */
      }
      const err = new ApiError(
        res.status,
        payload.error?.code ?? `http_${res.status}`,
        payload.error?.message ?? `Erreur ${res.status}`,
        payload.error?.details ?? {},
        correlationId,
      )
      if (res.status === 401 && !opts.silentUnauthorized) window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
      if (RETRYABLE_STATUS.has(res.status) && attempt < maxRetries) {
        lastError = err
        continue
      }
      throw err
    } catch (e) {
      if (e instanceof ApiError) throw e
      if (opts.signal?.aborted) throw e // annulation voulue par l'appelant
      const timedOut = controller.signal.aborted
      lastError = new ApiError(
        0,
        timedOut ? 'timeout' : 'network_error',
        timedOut
          ? 'Le serveur met trop de temps à répondre (démarrage à froid possible).'
          : 'Impossible de joindre le serveur.',
      )
      if (attempt >= maxRetries) throw lastError
    } finally {
      clearTimeout(timer)
      opts.signal?.removeEventListener('abort', onAbort)
    }
  }
  throw lastError ?? new ApiError(0, 'network_error', 'Impossible de joindre le serveur.')
}

/** Réveille un backend en veille (Render Free) sans bloquer l'interface : simple ping de liveness. */
export function warmUpBackend(): void {
  void fetch(`${API_BASE}/v1/health`, { method: 'GET', credentials: 'omit' }).catch(() => undefined)
}
