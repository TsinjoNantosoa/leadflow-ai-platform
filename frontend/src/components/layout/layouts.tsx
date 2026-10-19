import { Activity, Gauge, LogOut, Menu, Moon, ShieldCheck, Sun, Users, Zap, FileCheck2 } from 'lucide-react'
import * as React from 'react'
import { Link, NavLink, Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth, useTheme } from '@/app/providers'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Skeleton } from '@/components/ui/feedback'
import { cn, initials } from '@/lib/utils'
import { useOverview } from '@/hooks/queries'

export function Logo({ className, light = false }: { className?: string; light?: boolean }) {
  return (
    <span className={cn('inline-flex items-center gap-2 font-semibold tracking-tight', className)}>
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
        <Zap className="h-4 w-4" aria-hidden />
      </span>
      <span className={light ? 'text-sidebar-foreground' : undefined}>
        LeadFlow <span className="text-primary">AI</span>
      </span>
    </span>
  )
}

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, toggle } = useTheme()
  return (
    <Button
      variant="ghost"
      size="icon"
      className={className}
      onClick={toggle}
      aria-label={theme === 'dark' ? 'Passer au thème clair' : 'Passer au thème sombre'}
    >
      {theme === 'dark' ? <Sun className="h-4 w-4" aria-hidden /> : <Moon className="h-4 w-4" aria-hidden />}
    </Button>
  )
}

export function SkipLink() {
  return (
    <a
      href="#contenu"
      className="sr-only z-[100] rounded-md bg-primary px-4 py-2 text-primary-foreground focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
    >
      Aller au contenu
    </a>
  )
}

// --- Espace public --------------------------------------------------------------------------------------
export function PublicLayout() {
  const { status } = useAuth()
  return (
    <div className="flex min-h-dvh flex-col">
      <SkipLink />
      <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
          <Link to="/" aria-label="LeadFlow AI — accueil">
            <Logo />
          </Link>
          <nav aria-label="Navigation principale" className="hidden items-center gap-6 text-sm md:flex">
            <a href="/#fonctionnalites" className="text-muted-foreground transition-colors hover:text-foreground">Fonctionnalités</a>
            <a href="/#architecture" className="text-muted-foreground transition-colors hover:text-foreground">Architecture</a>
            <a href="/#novadigital" className="text-muted-foreground transition-colors hover:text-foreground">Cas d’usage</a>
          </nav>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Button asChild variant="ghost" size="sm" className="hidden sm:inline-flex">
              <Link to={status === 'authenticated' ? '/app/overview' : '/login'}>{status === 'authenticated' ? 'Tableau de bord' : 'Connexion'}</Link>
            </Button>
            <Button asChild size="sm">
              <Link to="/demo">Tester la démo</Link>
            </Button>
          </div>
        </div>
      </header>
      <main id="contenu" className="flex-1">
        <Outlet />
      </main>
      <footer className="border-t">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-8 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p>
            © LeadFlow AI — projet de démonstration. NovaDigital est une agence <strong>fictive</strong> ; toutes les données sont synthétiques.
          </p>
          <p className="flex items-center gap-1.5">
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden /> Aucun e-mail commercial n’est envoyé par cette version.
          </p>
        </div>
      </footer>
    </div>
  )
}

// --- Garde d'accès --------------------------------------------------------------------------------------
export function RequireAuth() {
  const { status } = useAuth()
  const location = useLocation()
  if (status === 'loading') {
    return (
      <div className="flex min-h-dvh items-center justify-center" role="status" aria-label="Chargement de la session">
        <Skeleton className="h-10 w-48" />
      </div>
    )
  }
  if (status === 'anonymous') return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  return <Outlet />
}

// --- Espace opérationnel ----------------------------------------------------------------------------------
const NAV = [
  { to: '/app/overview', label: 'Vue d’ensemble', icon: Gauge },
  { to: '/app/leads', label: 'Leads', icon: Users },
  { to: '/app/reviews', label: 'Revue humaine', icon: FileCheck2, badge: 'drafts' as const },
  { to: '/app/runs', label: 'Automatisations', icon: Activity, badge: 'incidents' as const },
]

function NavItems({ onNavigate }: { onNavigate?: () => void }) {
  const { data } = useOverview()
  const draftCount = data?.drafts.DRAFT ?? 0
  const incidents = (data?.outbox.DEAD_LETTER ?? 0) + (data?.outbox.RETRYING ?? 0)
  return (
    <nav aria-label="Navigation de l’application" className="flex flex-col gap-1">
      {NAV.map(({ to, label, icon: Icon, badge }) => {
        const count = badge === 'drafts' ? draftCount : badge === 'incidents' ? incidents : 0
        return (
          <NavLink
            key={to}
            to={to}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                'group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-white/10 text-white'
                  : 'text-sidebar-foreground/70 hover:bg-white/5 hover:text-sidebar-foreground',
              )
            }
          >
            <Icon className="h-4 w-4" aria-hidden />
            <span className="flex-1">{label}</span>
            {count > 0 && (
              <span
                className={cn(
                  'rounded-full px-1.5 py-0.5 text-[11px] font-semibold tabular-nums',
                  badge === 'incidents' ? 'bg-danger text-primary-foreground' : 'bg-primary text-primary-foreground',
                )}
                aria-label={`${count} ${badge === 'drafts' ? 'brouillons à examiner' : 'incidents'}`}
              >
                {count}
              </span>
            )}
          </NavLink>
        )
      })}
    </nav>
  )
}

function UserMenu() {
  const { user, logout } = useAuth()
  if (!user) return null
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="flex items-center gap-2 rounded-full border bg-card py-1 pl-1 pr-3 text-sm transition-colors hover:bg-muted"
          aria-label="Menu utilisateur"
        >
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary-soft text-xs font-semibold text-primary">
            {initials(user.full_name)}
          </span>
          <span className="hidden max-w-32 truncate sm:inline">{user.full_name}</span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>
          <span className="block truncate text-foreground">{user.email}</span>
          <span className="text-[11px] uppercase tracking-wide">{user.role === 'ADMIN' ? 'Administrateur' : 'Commercial'}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void logout()}>
          <LogOut className="h-4 w-4" aria-hidden /> Se déconnecter
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function AppShell() {
  const [open, setOpen] = React.useState(false)
  const { data } = useOverview()
  const demo = data?.data_origin.demo_leads ?? 0
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[17rem_1fr]">
      <SkipLink />
      <aside className="sticky top-0 hidden h-dvh flex-col gap-6 bg-sidebar p-4 lg:flex">
        <Link to="/" className="px-2 pt-2" aria-label="LeadFlow AI — site public">
          <Logo light />
        </Link>
        <NavItems />
        <div className="mt-auto rounded-lg border border-white/10 bg-white/5 p-3 text-xs text-sidebar-foreground/70">
          <p className="mb-1 flex items-center gap-1.5 font-medium text-sidebar-foreground">
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden /> Mode sûr
          </p>
          Les brouillons ne sont jamais envoyés : l’approbation est une décision interne.
        </div>
      </aside>

      <div className="flex min-w-0 flex-col">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b bg-background/85 px-4 backdrop-blur sm:px-6">
          <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setOpen(true)} aria-label="Ouvrir le menu">
            <Menu className="h-5 w-5" aria-hidden />
          </Button>
          <Link to="/" className="lg:hidden" aria-label="LeadFlow AI">
            <Logo />
          </Link>
          <div className="ml-auto flex items-center gap-2">
            <ThemeToggle />
            <UserMenu />
          </div>
        </header>
        {demo > 0 && (
          <div role="note" className="border-b border-primary/20 bg-primary-soft px-4 py-2 text-center text-xs text-primary sm:px-6">
            <strong>Données de démonstration :</strong> {demo} lead{demo > 1 ? 's' : ''} synthétique{demo > 1 ? 's' : ''} (adresses @example.org). Les
            indicateurs ci-dessous sont calculés sur la base, démonstration comprise.
          </div>
        )}
        <main id="contenu" className="mx-auto w-full max-w-7xl flex-1 animate-fade-in p-4 sm:p-6">
          <Outlet />
        </main>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="left-0 top-0 h-dvh w-72 max-w-[85vw] translate-x-0 translate-y-0 content-start rounded-none border-0 bg-sidebar p-4 text-sidebar-foreground">
          <DialogTitle className="sr-only">Menu</DialogTitle>
          <DialogDescription className="sr-only">Navigation de l’application</DialogDescription>
          <Logo light className="px-2 pt-2" />
          <NavItems onNavigate={() => setOpen(false)} />
        </DialogContent>
      </Dialog>
    </div>
  )
}
