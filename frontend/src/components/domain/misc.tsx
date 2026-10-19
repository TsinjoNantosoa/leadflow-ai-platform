import { Check, ChevronLeft, ChevronRight, Copy } from 'lucide-react'
import * as React from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export function CopyId({ value, className, label = 'Copier' }: { value: string; className?: string; label?: string }) {
  const [copied, setCopied] = React.useState(false)
  return (
    <span className={cn('inline-flex items-center gap-1.5', className)}>
      <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px]" title={value}>
        {value.slice(0, 8)}…
      </code>
      <button
        type="button"
        aria-label={`${label} ${value}`}
        className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(value)
            setCopied(true)
            setTimeout(() => setCopied(false), 1500)
          } catch {
            /* presse-papiers indisponible */
          }
        }}
      >
        {copied ? <Check className="h-3 w-3 text-success" aria-hidden /> : <Copy className="h-3 w-3" aria-hidden />}
      </button>
    </span>
  )
}

export function Pagination({
  page,
  pageSize,
  total,
  onPage,
  loading,
}: {
  page: number
  pageSize: number
  total: number
  onPage: (p: number) => void
  loading?: boolean
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1
  const to = Math.min(total, page * pageSize)
  return (
    <nav aria-label="Pagination" className="flex items-center justify-between gap-3 border-t px-4 py-3">
      <p className="text-xs text-muted-foreground" aria-live="polite">
        {total === 0 ? 'Aucun résultat' : `${from}–${to} sur ${total}`}
      </p>
      <div className="flex items-center gap-1.5">
        <Button variant="outline" size="sm" disabled={page <= 1 || loading} onClick={() => onPage(page - 1)} aria-label="Page précédente">
          <ChevronLeft className="h-4 w-4" aria-hidden />
        </Button>
        <span className="min-w-16 text-center text-xs tabular-nums">
          {page} / {pages}
        </span>
        <Button variant="outline" size="sm" disabled={page >= pages || loading} onClick={() => onPage(page + 1)} aria-label="Page suivante">
          <ChevronRight className="h-4 w-4" aria-hidden />
        </Button>
      </div>
    </nav>
  )
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}
