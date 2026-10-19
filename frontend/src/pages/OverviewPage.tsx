import { AlertTriangle, ArrowUpRight, FileCheck2, Flame, Inbox, ListChecks, Workflow } from 'lucide-react'
import type * as React from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { PageHeader } from '@/components/domain/misc'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/feedback'
import { useOverview } from '@/hooks/queries'
import { auditLabel, WORKFLOW_LABEL } from '@/lib/labels'
import { cn, formatDuration, formatRelative } from '@/lib/utils'
import type { Overview, Segment } from '@/types/api'

const SEGMENT_COLORS: Record<Segment, string> = { HOT: 'var(--hot)', WARM: 'var(--warm)', COLD: 'var(--cold)' }

function Kpi({
  label,
  value,
  icon: Icon,
  tone = 'primary',
  to,
  hint,
}: {
  label: string
  value: number | string
  icon: React.ElementType
  tone?: 'primary' | 'success' | 'warning' | 'danger'
  to?: string
  hint?: string
}) {
  const tones = {
    primary: 'bg-primary-soft text-primary',
    success: 'bg-success-soft text-success',
    warning: 'bg-warning-soft text-warning',
    danger: 'bg-danger-soft text-danger',
  }
  const body = (
    <Card className={cn('p-4 transition-shadow', to && 'hover:shadow-md')}>
      <div className="flex items-start justify-between">
        <span className={cn('flex h-9 w-9 items-center justify-center rounded-lg', tones[tone])}>
          <Icon className="h-4 w-4" aria-hidden />
        </span>
        {to && <ArrowUpRight className="h-4 w-4 text-muted-foreground" aria-hidden />}
      </div>
      <p className="mt-3 text-3xl font-semibold tabular-nums tracking-tight" data-testid={`kpi-${label}`}>
        {value}
      </p>
      <p className="text-sm text-muted-foreground">{label}</p>
      {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
    </Card>
  )
  return to ? (
    <Link to={to} className="block rounded-xl focus-visible:outline-2 focus-visible:outline-ring">
      {body}
    </Link>
  ) : (
    body
  )
}

function Content({ data }: { data: Overview }) {
  const total = data.leads.received
  const segTotal = data.segments.HOT + data.segments.WARM + data.segments.COLD
  const segData = (['HOT', 'WARM', 'COLD'] as Segment[]).map((s) => ({ name: s, value: data.segments[s] }))
  const workflows = Object.entries(data.runs_last_7_days)
  const incidents = (data.outbox.DEAD_LETTER ?? 0) + (data.outbox.RETRYING ?? 0)
  const lat = data.qualification_latency_seconds
  const perf = data.automation_performance

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <Kpi label="Leads reçus" value={total} icon={Inbox} to="/app/leads" />
        <Kpi label="Leads qualifiés" value={data.leads.qualified} icon={ListChecks} tone="success" to="/app/leads?status=READY" />
        <Kpi label="À examiner" value={data.leads.manual_review} icon={FileCheck2} tone="warning" to="/app/leads?status=MANUAL_REVIEW" />
        <Kpi label="Échecs" value={data.leads.failed} icon={AlertTriangle} tone="danger" to="/app/leads?status=FAILED" />
        <Kpi label="En cours" value={data.leads.in_progress} icon={Workflow} hint="Nouveaux + en traitement" />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Évolution des demandes</CardTitle>
            <CardDescription>Demandes reçues par jour sur {data.series.length} jours (UTC)</CardDescription>
          </CardHeader>
          <CardContent>
            {total === 0 ? (
              <EmptyState title="Aucune demande pour l’instant" description="Soumettez une demande via la page de démo pour alimenter ce graphique." />
            ) : (
              <div className="h-56 w-full" role="img" aria-label="Histogramme des demandes reçues par jour">
                <ResponsiveContainer>
                  <BarChart data={data.series} margin={{ left: -20, right: 4, top: 8 }}>
                    <CartesianGrid vertical={false} stroke="var(--border)" />
                    <XAxis
                      dataKey="date"
                      tickFormatter={(d: string) => d.slice(8, 10) + '/' + d.slice(5, 7)}
                      tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
                      axisLine={false}
                      tickLine={false}
                      interval="preserveStartEnd"
                    />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }} axisLine={false} tickLine={false} />
                    <Tooltip
                      cursor={{ fill: 'var(--muted)' }}
                      contentStyle={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }}
                      labelFormatter={(d: string) => new Date(d).toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' })}
                      formatter={(v: number) => [v, 'Demandes']}
                    />
                    <Bar dataKey="count" fill="var(--primary)" radius={[4, 4, 0, 0]} maxBarSize={28} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Segments</CardTitle>
            <CardDescription>Dernière qualification de chaque lead</CardDescription>
          </CardHeader>
          <CardContent>
            {segTotal === 0 ? (
              <EmptyState title="Aucun lead qualifié" />
            ) : (
              <div className="flex items-center gap-4">
                <div className="h-32 w-32 shrink-0" role="img" aria-label={`HOT ${data.segments.HOT}, WARM ${data.segments.WARM}, COLD ${data.segments.COLD}`}>
                  <ResponsiveContainer>
                    <PieChart>
                      <Pie data={segData} dataKey="value" innerRadius={36} outerRadius={60} paddingAngle={2} stroke="none">
                        {segData.map((s) => (
                          <Cell key={s.name} fill={SEGMENT_COLORS[s.name as Segment]} />
                        ))}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <ul className="flex-1 space-y-2 text-sm">
                  {segData.map((s) => (
                    <li key={s.name} className="flex items-center justify-between">
                      <span className="flex items-center gap-2">
                        <span className="h-2.5 w-2.5 rounded-full" style={{ background: SEGMENT_COLORS[s.name as Segment] }} aria-hidden />
                        {s.name}
                      </span>
                      <span className="font-semibold tabular-nums">{s.value}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Automatisations (7 jours)</CardTitle>
            <CardDescription>Exécutions par workflow et statut</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {workflows.length === 0 ? (
              <EmptyState title="Aucune exécution" description="Les workflows n8n n’ont pas encore traité d’événement." />
            ) : (
              workflows.map(([wf, st]) => {
                const sum = Object.values(st).reduce((a, b) => a + (b ?? 0), 0)
                const ok = st.SUCCEEDED ?? 0
                const bad = (st.FAILED ?? 0) + (st.RETRYING ?? 0)
                return (
                  <div key={wf}>
                    <div className="mb-1 flex justify-between text-sm">
                      <span>{WORKFLOW_LABEL[wf] ?? wf}</span>
                      <span className="tabular-nums text-muted-foreground">{sum}</span>
                    </div>
                    <div className="flex h-2 overflow-hidden rounded-full bg-muted" aria-hidden>
                      <span className="bg-success" style={{ width: `${(ok / sum) * 100}%` }} />
                      <span className="bg-warning" style={{ width: `${((sum - ok - bad) / sum) * 100}%` }} />
                      <span className="bg-danger" style={{ width: `${(bad / sum) * 100}%` }} />
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {ok} réussie{ok > 1 ? 's' : ''} · {bad} en échec ou reprise
                    </p>
                  </div>
                )
              })
            )}
            {incidents > 0 && (
              <Link to="/app/runs" className="mt-2 flex items-center gap-2 rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">
                <AlertTriangle className="h-4 w-4" aria-hidden /> {incidents} événement{incidents > 1 ? 's' : ''} en reprise ou abandonné{incidents > 1 ? 's' : ''}
              </Link>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Pipeline commercial</CardTitle>
            <CardDescription>Brouillons et synchronisation CRM</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div>
              <p className="mb-1.5 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                <Flame className="h-3 w-3" aria-hidden /> Brouillons
              </p>
              <dl className="grid grid-cols-3 gap-2 text-center">
                {[
                  ['À examiner', data.drafts.DRAFT ?? 0],
                  ['Approuvés', data.drafts.APPROVED ?? 0],
                  ['Rejetés', data.drafts.REJECTED ?? 0],
                ].map(([l, v]) => (
                  <div key={l} className="rounded-lg bg-muted/60 p-2">
                    <dd className="text-xl font-semibold tabular-nums">{v}</dd>
                    <dt className="text-[11px] text-muted-foreground">{l}</dt>
                  </div>
                ))}
              </dl>
            </div>
            <div>
              <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">CRM</p>
              <dl className="grid grid-cols-3 gap-2 text-center">
                {[
                  ['Synchronisés', data.crm.SYNCED ?? 0],
                  ['En reprise', data.crm.RETRYING ?? 0],
                  ['En échec', data.crm.FAILED ?? 0],
                ].map(([l, v]) => (
                  <div key={l} className="rounded-lg bg-muted/60 p-2">
                    <dd className="text-xl font-semibold tabular-nums">{v}</dd>
                    <dt className="text-[11px] text-muted-foreground">{l}</dt>
                  </div>
                ))}
              </dl>
            </div>
            <p className="text-xs text-muted-foreground">
              {lat.samples > 0 && lat.p50 !== null
                ? `Délai réception → qualification (non démo, ${lat.samples} mesure${lat.samples > 1 ? 's' : ''}) : médiane ${formatDuration(lat.p50 * 1000)}${lat.p95 !== null ? `, p95 ${formatDuration(lat.p95 * 1000)}` : ''}.`
                : 'Aucune mesure de délai de qualification disponible (les leads de démonstration sont exclus).'}
            </p>
            <p className="text-xs text-muted-foreground" data-testid="automation-performance">
              {perf.successful_runs_7d > 0 && perf.avg_duration_ms !== null
                ? `Traitements réussis (7 j) : ${perf.successful_runs_7d}, durée moyenne ${formatDuration(perf.avg_duration_ms)}${perf.p95_duration_ms !== null ? `, p95 ${formatDuration(perf.p95_duration_ms)}` : ''}. `
                : 'Aucun traitement réussi sur 7 jours. '}
              Reprises cumulées : {perf.retries_total} · dead-letters : {perf.dead_letter}.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Activité récente</CardTitle>
            <CardDescription>Derniers événements enregistrés</CardDescription>
          </CardHeader>
          <CardContent>
            {data.recent_activity.length === 0 ? (
              <EmptyState title="Aucune activité" />
            ) : (
              <ul className="space-y-3">
                {data.recent_activity.slice(0, 7).map((a) => (
                  <li key={a.id} className="flex gap-2.5 text-sm">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" aria-hidden />
                    <div className="min-w-0">
                      <p className="truncate">
                        {a.lead_id ? (
                          <Link to={`/app/leads/${a.lead_id}`} className="font-medium hover:underline">
                            {a.lead_name ?? 'Lead'}
                          </Link>
                        ) : (
                          'Système'
                        )}{' '}
                        <span className="text-muted-foreground">— {auditLabel(a.action)}</span>
                      </p>
                      <p className="text-xs text-muted-foreground">{formatRelative(a.created_at)}</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      {data.llm_usage.calls > 0 && (
        <p className="text-xs text-muted-foreground">
          Consommation IA réelle (appels non mock) : {data.llm_usage.calls} appels, {data.llm_usage.input_tokens.toLocaleString('fr-FR')} tokens en entrée,{' '}
          {data.llm_usage.output_tokens.toLocaleString('fr-FR')} en sortie
          {data.llm_usage.estimated_cost_usd !== null ? `, coût estimé ${data.llm_usage.estimated_cost_usd.toFixed(4)} USD (tarifs configurés)` : ' (aucun tarif configuré : pas d’estimation de coût)'}.
        </p>
      )}
    </div>
  )
}

export default function OverviewPage() {
  const { data, isPending, error, refetch } = useOverview()
  return (
    <div className="space-y-6">
      <PageHeader
        title="Vue d’ensemble"
        description={data ? `Calculé depuis PostgreSQL · mis à jour ${formatRelative(data.generated_at)}` : 'Indicateurs calculés depuis PostgreSQL'}
      />
      {isPending ? (
        <div className="space-y-4" role="status" aria-label="Chargement des indicateurs">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-32" />
            ))}
          </div>
          <Skeleton className="h-72" />
        </div>
      ) : error ? (
        <Card>
          <ErrorState error={error} onRetry={() => void refetch()} />
        </Card>
      ) : (
        <Content data={data} />
      )}
    </div>
  )
}
