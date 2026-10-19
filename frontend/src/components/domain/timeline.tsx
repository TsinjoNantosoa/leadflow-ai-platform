import { AlertTriangle, Check, CircleDashed, Loader2, MinusCircle, X } from 'lucide-react'
import type * as React from 'react'
import { cn, formatDateTime } from '@/lib/utils'
import type { TimelineState, TimelineStep } from '@/types/api'

const stateStyle: Record<TimelineState, { icon: React.ElementType; dot: string; label: string; line: string }> = {
  done: { icon: Check, dot: 'bg-success text-primary-foreground', label: 'Terminé', line: 'bg-success/50' },
  pending: { icon: CircleDashed, dot: 'bg-muted text-muted-foreground border border-border', label: 'À venir', line: 'bg-border' },
  in_progress: { icon: Loader2, dot: 'bg-info text-primary-foreground', label: 'En cours', line: 'bg-border' },
  attention: { icon: AlertTriangle, dot: 'bg-warning text-primary-foreground animate-pulse-ring', label: 'Action attendue', line: 'bg-border' },
  failed: { icon: X, dot: 'bg-danger text-primary-foreground', label: 'Échec', line: 'bg-danger/40' },
  skipped: { icon: MinusCircle, dot: 'bg-muted text-muted-foreground border border-dashed', label: 'Non réalisé', line: 'bg-border' },
}

/**
 * Parcours d'un lead. Chaque étape reflète un enregistrement réel (lead, qualification, mapping CRM, brouillon, audit) :
 * aucune animation ne simule un succès, une étape « à venir » reste grisée tant que la base n'en contient pas la trace.
 */
export function LeadTimeline({ steps }: { steps: TimelineStep[] }) {
  return (
    <ol aria-label="Parcours du lead" className="relative">
      {steps.map((s, i) => {
        const st = stateStyle[s.state]
        const Icon = st.icon
        const last = i === steps.length - 1
        return (
          <li key={s.key} className="relative flex gap-3 pb-5 last:pb-0" data-state={s.state}>
            {!last && <span className={cn('absolute left-[13px] top-7 h-[calc(100%-1.75rem)] w-0.5', st.line)} aria-hidden />}
            <span className={cn('relative z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full', st.dot)}>
              <Icon className={cn('h-3.5 w-3.5', s.state === 'in_progress' && 'animate-spin')} aria-hidden />
            </span>
            <div className="min-w-0 flex-1 pt-0.5">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                <p className={cn('text-sm font-medium', s.state === 'pending' && 'text-muted-foreground')}>
                  {s.label}
                  <span className="sr-only"> — {st.label}</span>
                </p>
                <time className="text-xs text-muted-foreground" dateTime={s.at ?? undefined}>
                  {s.at ? formatDateTime(s.at) : st.label}
                </time>
              </div>
              {s.detail && <p className="mt-0.5 break-words text-xs text-muted-foreground">{s.detail}</p>}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
