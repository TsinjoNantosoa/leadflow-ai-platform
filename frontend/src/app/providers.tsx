import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import * as React from 'react'
import { Toaster } from 'sonner'
import { ApiError, UNAUTHORIZED_EVENT } from '@/lib/api'
import { authService } from '@/services/api-services'
import type { Role, User } from '@/types/api'

// --- Thème ---------------------------------------------------------------------------------------
type Theme = 'light' | 'dark'
interface ThemeCtx {
  theme: Theme
  toggle: () => void
}
const ThemeContext = React.createContext<ThemeCtx | null>(null)

function readTheme(): Theme {
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light'
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = React.useState<Theme>(readTheme)
  const toggle = React.useCallback(() => {
    setTheme((t) => {
      const next: Theme = t === 'dark' ? 'light' : 'dark'
      document.documentElement.classList.toggle('dark', next === 'dark')
      try {
        localStorage.setItem('lf-theme', next)
      } catch {
        /* stockage indisponible : le thème reste valable pour la session */
      }
      return next
    })
  }, [])
  const value = React.useMemo(() => ({ theme, toggle }), [theme, toggle])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeCtx {
  const ctx = React.useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme doit être utilisé dans <ThemeProvider>')
  return ctx
}

// --- Authentification ----------------------------------------------------------------------------
type AuthStatus = 'loading' | 'authenticated' | 'anonymous'
interface AuthCtx {
  status: AuthStatus
  user: User | null
  login: (email: string, password: string) => Promise<User>
  logout: () => Promise<void>
  hasRole: (...roles: Role[]) => boolean
}
const AuthContext = React.createContext<AuthCtx | null>(null)

export function AuthProvider({ children, queryClient }: { children: React.ReactNode; queryClient: QueryClient }) {
  const [status, setStatus] = React.useState<AuthStatus>('loading')
  const [user, setUser] = React.useState<User | null>(null)

  React.useEffect(() => {
    let cancelled = false
    authService
      .me()
      .then((s) => {
        if (cancelled) return
        setUser(s?.user ?? null)
        setStatus(s ? 'authenticated' : 'anonymous')
      })
      .catch(() => {
        // Serveur injoignable : on ne prétend pas connaître la session ; l'utilisateur sera renvoyé vers /login.
        if (!cancelled) setStatus('anonymous')
      })
    return () => {
      cancelled = true
    }
  }, [])

  React.useEffect(() => {
    const onUnauthorized = () => {
      setUser(null)
      setStatus('anonymous')
      queryClient.clear()
    }
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
  }, [queryClient])

  const value = React.useMemo<AuthCtx>(
    () => ({
      status,
      user,
      login: async (email, password) => {
        const s = await authService.login(email, password)
        setUser(s.user)
        setStatus('authenticated')
        return s.user
      },
      logout: async () => {
        try {
          await authService.logout()
        } finally {
          setUser(null)
          setStatus('anonymous')
          queryClient.clear()
        }
      },
      hasRole: (...roles) => (user ? roles.includes(user.role) : false),
    }),
    [status, user, queryClient],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthCtx {
  const ctx = React.useContext(AuthContext)
  if (!ctx) throw new Error('useAuth doit être utilisé dans <AuthProvider>')
  return ctx
}

// --- Racine ----------------------------------------------------------------------------------------
export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        refetchOnWindowFocus: false,
        // apiFetch reprend déjà les erreurs réseau / 502-504 : pas de double politique de reprise ici.
        retry: false,
      },
      mutations: { retry: false },
    },
  })
}

export function AppProviders({ children, queryClient }: { children: React.ReactNode; queryClient: QueryClient }) {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <AuthProvider queryClient={queryClient}>
          {children}
          <Toaster richColors closeButton position="bottom-right" />
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}

export const isApiError = (e: unknown): e is ApiError => e instanceof ApiError
