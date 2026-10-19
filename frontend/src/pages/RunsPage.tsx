import { RotateCw } from 'lucide-react'
import * as React from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '@/app/providers'
import { DemoBadge, OutboxBadge, RunBadge } from '@/components/domain/badges'
import { CopyId, PageHeader, Pagination } from '@/components/domain/misc'
import { Alert, EmptyState, ErrorState, Skeleton } from '@/components/ui/feedback'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Select } from '@/components/ui/form-controls'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { useRetryRun, useRuns } from '@/hooks/queries'
import { RUN_STATUS, WORKFLOW_LABEL } from '@/lib/labels'
import { formatDateTime, formatDuration, formatRelative } from '@/lib/utils'
import type { RunStatus } from '@/types/api'

export default function RunsPage() {
  const { hasRole } = useAuth()
  const isAdmin = hasRole('ADMIN')
  const [page, setPage] = React.useState(1)
  const [status, setStatus] = React.useState<RunStatus | ''>('')
  const [workflow, setWorkflow] = React.useState('')
  const { data, isPending, isFetching, error, refetch } = useRuns({ page, status, workflow: workflow || undefined })
  const retry = useRetryRun()

  return (
    <div className="space-y-6">
      <PageHeader title="Automatisations" description="Supervision des workflows n8n : statuts, durées, tentatives, erreurs et reprises." />
      <Alert tone="info" title="Le backend est l’unique autorité des reprises">
        Les tentatives, délais (backoff) et abandons (dead-letter) sont décidés côté API. La « reprise manuelle » replanifie l’événement ; le workflow de
        supervision le prendra au prochain passage.
      </Alert>

      <Card>
        <div className="flex flex-wrap gap-3 border-b p-4">
          <Select aria-label="Filtrer par statut" className="w-44" value={status} onChange={(e) => { setStatus(e.target.value as RunStatus | ''); setPage(1) }}>
            <option value="">Tous les statuts</option>
            {(Object.keys(RUN_STATUS) as RunStatus[]).map((s) => <option key={s} value={s}>{RUN_STATUS[s].label}</option>)}
          </Select>
          <Select aria-label="Filtrer par workflow" className="w-56" value={workflow} onChange={(e) => { setWorkflow(e.target.value); setPage(1) }}>
            <option value="">Tous les workflows</option>
            {Object.entries(WORKFLOW_LABEL).filter(([k]) => !k.includes('WF-04')).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
        </div>

        {isPending ? (
          <div className="space-y-2 p-4" role="status" aria-label="Chargement des exécutions">
            {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-12" />)}
          </div>
        ) : error ? (
          <ErrorState error={error} onRetry={() => void refetch()} />
        ) : data.items.length === 0 ? (
          <EmptyState title="Aucune exécution" description="Les exécutions apparaissent dès que n8n réserve un événement de l’outbox." />
        ) : (
          <>
            <div className={isFetching ? 'opacity-70 transition-opacity' : 'transition-opacity'}>
              <Table aria-label="Exécutions des automatisations">
                <THead>
                  <TR className="hover:bg-transparent">
                    <TH>Workflow</TH><TH>Statut</TH><TH>Tentative</TH><TH>Durée</TH><TH>Erreur</TH>
                    <TH className="hidden lg:table-cell">Corrélation</TH><TH>Début</TH><TH><span className="sr-only">Actions</span></TH>
                  </TR>
                </THead>
                <TBody>
                  {data.items.map((r) => (
                    <TR key={r.id}>
                      <TD>
                        <span className="flex items-center gap-2 font-medium">{WORKFLOW_LABEL[r.workflow_name] ?? r.workflow_name}<DemoBadge show={r.is_demo} /></span>
                        <span className="text-xs text-muted-foreground">
                          {r.lead_id ? <Link to={`/app/leads/${r.lead_id}`} className="hover:underline">voir le lead</Link> : '—'} · {r.event_type}
                        </span>
                      </TD>
                      <TD>
                        <span className="flex flex-col items-start gap-1">
                          <RunBadge status={r.status} />
                          {r.event_status && r.event_status !== 'DELIVERED' && <OutboxBadge status={r.event_status} />}
                        </span>
                      </TD>
                      <TD className="tabular-nums">{r.attempt_count}{r.max_attempts ? ` / ${r.max_attempts}` : ''}</TD>
                      <TD className="whitespace-nowrap tabular-nums">{formatDuration(r.duration_ms)}</TD>
                      <TD>
                        {r.error_code ? <code className="rounded bg-danger-soft px-1.5 py-0.5 text-xs text-danger">{r.error_code}</code> : <span className="text-muted-foreground">—</span>}
                        {r.event_status === 'RETRYING' && r.next_attempt_at && (
                          <span className="mt-1 block text-xs text-muted-foreground">prochaine tentative {formatRelative(r.next_attempt_at)}</span>
                        )}
                      </TD>
                      <TD className="hidden lg:table-cell"><CopyId value={r.correlation_id} label="Copier l’identifiant de corrélation" /></TD>
                      <TD className="whitespace-nowrap text-xs text-muted-foreground">{formatDateTime(r.started_at)}</TD>
                      <TD>
                        {r.can_retry && isAdmin && (
                          <Button variant="outline" size="sm" loading={retry.isPending && retry.variables === r.id} onClick={() => retry.mutate(r.id)}>
                            <RotateCw className="h-3.5 w-3.5" aria-hidden /> Reprise manuelle
                          </Button>
                        )}
                        {r.can_retry && !isAdmin && <span className="text-xs text-muted-foreground">Admin requis</span>}
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </div>
            <Pagination page={data.page} pageSize={data.page_size} total={data.total} loading={isFetching} onPage={setPage} />
          </>
        )}
      </Card>
    </div>
  )
}
