import { AlertCircle, AlertTriangle, CheckCircle2, Inbox, Info, RefreshCw } from 'lucide-react'
import * as React from 'react'
import { Button } from '@/components/ui/button'
import { ApiError } from '@/lib/api'
import { cn } from '@/lib/utils'

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div aria-hidden className={cn('animate-pulse rounded-md bg-muted', className)} {...props} />
}

type AlertTone = 'info' | 'success' | 'warning' | 'danger'
const alertStyles: Record<AlertTone, { box: string; icon: React.ElementType }> = {
  info: { box: 'border-info/30 bg-info-soft text-foreground [&>svg]:text-info', icon: Info },
  success: { box: 'border-success/30 bg-success-soft text-foreground [&>svg]:text-success', icon: CheckCircle2 },
  warning: { box: 'border-warning/40 bg-warning-soft text-foreground [&>svg]:text-warning', icon: AlertTriangle },
  danger: { box: 'border-danger/30 bg-danger-soft text-foreground [&>svg]:text-danger', icon: AlertCircle },
}

export function Alert({
  tone = 'info',
  title,
  children,
  className,
  role,
}: {
  tone?: AlertTone
  title?: string
  children?: React.ReactNode
  className?: string
  role?: string
}) {
  const { box, icon: Icon } = alertStyles[tone]
  return (
    <div role={role ?? (tone === 'danger' ? 'alert' : 'status')} className={cn('flex gap-3 rounded-lg border p-3.5 text-sm', box, className)}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div className="min-w-0 space-y-0.5">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className="text-muted-foreground">{children}</div>}
      </div>
    </div>
  )
}

export function EmptyState({
  title,
  description,
  icon: Icon = Inbox,
  action,
}: {
  title: string
  description?: string
  icon?: React.ElementType
  action?: React.ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-14 text-center">
      <div className="flex h-11 w-11 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <Icon className="h-5 w-5" aria-hidden />
      </div>
      <p className="text-sm font-medium">{title}</p>
      {description && <p className="max-w-sm text-xs text-muted-foreground">{description}</p>}
      {action}
    </div>
  )
}

export function errorMessage(error: unknown): { title: string; detail: string; correlationId: string | null } {
  if (error instanceof ApiError) {
    if (error.isNetwork) {
      return {
        title: 'Serveur injoignable',
        detail: `${error.message} Le serveur gratuit se réveille parfois en ~1 minute : réessayez.`,
        correlationId: null,
      }
    }
    if (error.status === 403) return { title: 'Accès refusé', detail: 'Vous n’avez pas les droits pour cette action.', correlationId: error.correlationId }
    if (error.status === 429) return { title: 'Trop de requêtes', detail: 'Réessayez dans quelques instants.', correlationId: error.correlationId }
    return { title: 'Une erreur est survenue', detail: error.message, correlationId: error.correlationId }
  }
  return { title: 'Une erreur est survenue', detail: 'Réessayez ou rechargez la page.', correlationId: null }
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { title, detail, correlationId } = errorMessage(error)
  return (
    <div role="alert" className="flex flex-col items-center gap-2 px-6 py-12 text-center">
      <div className="flex h-11 w-11 items-center justify-center rounded-full bg-danger-soft text-danger">
        <AlertCircle className="h-5 w-5" aria-hidden />
      </div>
      <p className="text-sm font-medium">{title}</p>
      <p className="max-w-md text-xs text-muted-foreground">{detail}</p>
      {correlationId && <p className="font-mono text-[11px] text-muted-foreground">Référence : {correlationId}</p>}
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry} className="mt-2">
          <RefreshCw className="h-3.5 w-3.5" aria-hidden /> Réessayer
        </Button>
      )}
    </div>
  )
}
