import { ArrowLeft, Building2, Mail, MessageSquareQuote, Phone, RefreshCw, ShieldAlert, Sparkles } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { CrmBadge, DemoBadge, FollowupBadge, LeadStatusBadge, RunBadge, ReviewFlag } from '@/components/domain/badges'
import { CopyId } from '@/components/domain/misc'
import { ScoreBreakdown } from '@/components/domain/score'
import { LeadTimeline } from '@/components/domain/timeline'
import { Alert, ErrorState, Skeleton } from '@/components/ui/feedback'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useLead, useRetryLead } from '@/hooks/queries'
import { ApiError } from '@/lib/api'
import { auditLabel, serviceLabel, reviewReason, WORKFLOW_LABEL } from '@/lib/labels'
import { formatDateTime, formatDuration, formatMoney } from '@/lib/utils'
import type { LeadDetail } from '@/types/api'

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm font-medium">{children}</dd>
    </div>
  )
}

function Content({ lead }: { lead: LeadDetail }) {
  const retry = useRetryLead()
  const q = lead.qualification
  const canRetry = lead.status !== 'ARCHIVED' && lead.status !== 'PROCESSING'
  const evidence = q?.extracted_data.evidence ?? []
  const latestFollowup = lead.followups[0]

  return (
    <div className="space-y-6">
      <div className="space-y-4">
        <Button asChild variant="ghost" size="sm" className="-ml-2">
          <Link to="/app/leads">
            <ArrowLeft className="h-4 w-4" aria-hidden /> Retour aux leads
          </Link>
        </Button>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-semibold tracking-tight">{lead.contact.full_name}</h1>
              <DemoBadge show={lead.is_demo} />
              <LeadStatusBadge status={lead.status} />
              {q?.human_review_required && <ReviewFlag />}
            </div>
            <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
              {lead.contact.company && <span className="inline-flex items-center gap-1.5"><Building2 className="h-3.5 w-3.5" aria-hidden />{lead.contact.company}</span>}
              <span className="inline-flex items-center gap-1.5"><Mail className="h-3.5 w-3.5" aria-hidden />{lead.contact.email}</span>
              {lead.contact.phone && <span className="inline-flex items-center gap-1.5"><Phone className="h-3.5 w-3.5" aria-hidden />{lead.contact.phone}</span>}
              {lead.contact.lead_count > 1 && <span>{lead.contact.lead_count} demandes de ce contact</span>}
            </p>
          </div>
          <Button variant="outline" onClick={() => retry.mutate(lead.id)} loading={retry.isPending} disabled={!canRetry}>
            {!retry.isPending && <RefreshCw className="h-4 w-4" aria-hidden />} Relancer le traitement
          </Button>
        </div>
      </div>

      {(lead.status === 'MANUAL_REVIEW' || (q && q.review_reasons.length > 0)) && (
        <Alert tone="warning" title="Cette demande nécessite un examen humain">
          {q && q.review_reasons.length > 0 ? (
            <ul className="list-inside list-disc">
              {q.review_reasons.map((r) => <li key={r}>{reviewReason(r)}</li>)}
            </ul>
          ) : (
            reviewReason(lead.status_reason ?? 'Qualification automatique impossible')
          )}
        </Alert>
      )}
      {lead.status === 'FAILED' && (
        <Alert tone="danger" title="Le traitement automatique a échoué">
          Code : <code>{lead.status_reason ?? 'inconnu'}</code>. Consultez l’onglet « Traitements » puis relancez.
        </Alert>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <div className="min-w-0 space-y-6">
          <Tabs defaultValue="request">
            <TabsList aria-label="Sections du lead">
              <TabsTrigger value="request">Demande</TabsTrigger>
              <TabsTrigger value="score">Score</TabsTrigger>
              <TabsTrigger value="draft">Brouillon{latestFollowup ? ` (${lead.followups.length})` : ''}</TabsTrigger>
              <TabsTrigger value="runs">Traitements ({lead.runs.length})</TabsTrigger>
              <TabsTrigger value="audit">Audit ({lead.audit.length})</TabsTrigger>
            </TabsList>

            <TabsContent value="request" className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2"><MessageSquareQuote className="h-4 w-4" aria-hidden /> Demande originale</CardTitle>
                  <CardDescription>
                    Reçue le {formatDateTime(lead.created_at)} · source {lead.source}
                    {lead.requested_service && <> · service demandé : {serviceLabel(lead.requested_service)}</>}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {/* Texte non fiable : rendu en texte brut (jamais en HTML) */}
                  <blockquote className="whitespace-pre-wrap break-words rounded-lg border-l-4 border-primary/40 bg-muted/50 p-4 text-sm leading-relaxed">
                    {lead.message}
                  </blockquote>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2"><Sparkles className="h-4 w-4" aria-hidden /> Informations extraites par l’IA</CardTitle>
                  <CardDescription>
                    {q ? `${q.llm_provider ?? '—'} · ${q.model_name ?? '—'} · prompt ${q.prompt_version ?? '—'}` : 'Pas encore de qualification'}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {q ? (
                    <div className="space-y-4">
                      <p className="rounded-lg bg-primary-soft p-3 text-sm">{q.summary}</p>
                      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                        <Fact label="Service identifié">{serviceLabel(q.service)}</Fact>
                        <Fact label="Intention">{q.intent}</Fact>
                        <Fact label="Langue">{q.language ?? '—'}</Fact>
                        <Fact label="Budget">{formatMoney(q.budget_amount, q.budget_currency)}</Fact>
                        <Fact label="Échéance">{q.timeline_days !== null ? `${q.timeline_days} jours` : 'Non précisée'}</Fact>
                        <Fact label="Clarté du besoin">{q.need_clarity ?? '—'}</Fact>
                      </dl>
                      {evidence.length > 0 && (
                        <div>
                          <p className="mb-1.5 text-xs text-muted-foreground">Citations retrouvées dans le message</p>
                          <ul className="space-y-1.5">
                            {evidence.map((e) => (
                              <li key={e} className="rounded border-l-2 border-primary/50 bg-muted/50 px-3 py-1.5 text-sm italic">« {e} »</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      <p className="text-xs text-muted-foreground">
                        Les valeurs absentes du message restent vides : l’IA n’invente ni budget, ni échéance. Qualification v{q.version}
                        {lead.qualification_history.length > 1 && <> (historique : {lead.qualification_history.map((h) => `v${h.version}=${h.score}`).join(', ')})</>}.
                      </p>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">En attente du traitement par le workflow de qualification.</p>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="score">
              <Card>
                <CardHeader><CardTitle>Score explicable</CardTitle></CardHeader>
                <CardContent>
                  {q ? <ScoreBreakdown qualification={q} /> : <p className="text-sm text-muted-foreground">Aucun score : le lead n’est pas qualifié.</p>}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="draft" className="space-y-4">
              {lead.followups.length === 0 ? (
                <Card><CardContent className="p-6 text-sm text-muted-foreground">Aucun brouillon généré pour ce lead.</CardContent></Card>
              ) : (
                lead.followups.map((f) => (
                  <Card key={f.id}>
                    <CardHeader className="flex-row items-center justify-between">
                      <CardTitle>{f.subject}</CardTitle>
                      <FollowupBadge status={f.status} />
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <pre className="whitespace-pre-wrap break-words rounded-lg bg-muted/50 p-4 font-sans text-sm leading-relaxed">{f.body}</pre>
                      <p className="text-xs text-muted-foreground">
                        Rédigé par {f.llm_provider ?? '—'} · {f.model_name ?? '—'} · Aucun e-mail n’a été envoyé.
                      </p>
                      <Button asChild variant="outline" size="sm"><Link to="/app/reviews">Ouvrir le centre de revue</Link></Button>
                    </CardContent>
                  </Card>
                ))
              )}
            </TabsContent>

            <TabsContent value="runs">
              <Card>
                <CardContent className="p-0">
                  {lead.runs.length === 0 ? (
                    <p className="p-6 text-sm text-muted-foreground">Aucune exécution enregistrée.</p>
                  ) : (
                    <ul className="divide-y">
                      {lead.runs.map((r) => (
                        <li key={r.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 p-4 text-sm">
                          <span className="min-w-40 font-medium">{WORKFLOW_LABEL[r.workflow_name] ?? r.workflow_name}</span>
                          <RunBadge status={r.status} />
                          <span className="text-xs text-muted-foreground">tentative {r.attempt_count}{r.max_attempts ? `/${r.max_attempts}` : ''}</span>
                          <span className="text-xs text-muted-foreground">{formatDuration(r.duration_ms)}</span>
                          {r.error_code && <code className="rounded bg-danger-soft px-1.5 py-0.5 text-xs text-danger">{r.error_code}</code>}
                          <span className="ml-auto text-xs text-muted-foreground">{formatDateTime(r.started_at)}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="audit">
              <Card>
                <CardContent className="p-0">
                  <ul className="divide-y">
                    {lead.audit.map((a) => (
                      <li key={a.id} className="flex flex-wrap items-center gap-x-3 gap-y-0.5 px-4 py-3 text-sm">
                        <span className="font-medium">{auditLabel(a.action)}</span>
                        <span className="text-xs text-muted-foreground">
                          {a.actor_type === 'user' ? a.actor_ref : a.actor_type === 'service' ? 'automatisation' : 'système'}
                        </span>
                        <time className="ml-auto text-xs text-muted-foreground" dateTime={a.created_at}>{formatDateTime(a.created_at)}</time>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>

        <aside className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Parcours du lead</CardTitle>
              <CardDescription>Chaque étape reflète un enregistrement réel</CardDescription>
            </CardHeader>
            <CardContent><LeadTimeline steps={lead.timeline} /></CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>État CRM</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              {lead.crm ? (
                <>
                  <div className="flex items-center justify-between"><span className="text-muted-foreground">Statut</span><CrmBadge status={lead.crm.sync_status} /></div>
                  <div className="flex items-center justify-between"><span className="text-muted-foreground">Fournisseur</span><span className="font-medium">{lead.crm.provider}</span></div>
                  <div className="flex items-center justify-between"><span className="text-muted-foreground">Tentatives</span><span className="tabular-nums">{lead.crm.attempt_count}</span></div>
                  {lead.crm.external_contact_id && <div className="flex items-center justify-between"><span className="text-muted-foreground">Identifiant externe</span><code className="text-xs">{lead.crm.external_contact_id}</code></div>}
                  {lead.crm.last_error_code && <p className="flex items-center gap-1.5 text-xs text-danger"><ShieldAlert className="h-3.5 w-3.5" aria-hidden />Dernière erreur : {lead.crm.last_error_code}</p>}
                </>
              ) : (
                <p className="text-muted-foreground">Pas encore synchronisé.</p>
              )}
            </CardContent>
          </Card>

          <p className="px-1 text-xs text-muted-foreground">
            Lead <CopyId value={lead.id} /> · consentement données v{lead.privacy_notice_version ?? '—'}
          </p>
        </aside>
      </div>
    </div>
  )
}

export default function LeadDetailPage() {
  const { id = '' } = useParams()
  const { data, isPending, error, refetch } = useLead(id)
  if (isPending) {
    return (
      <div className="space-y-4" role="status" aria-label="Chargement du lead">
        <Skeleton className="h-9 w-72" />
        <Skeleton className="h-64" />
      </div>
    )
  }
  if (error) {
    const notFound = error instanceof ApiError && error.status === 404
    return (
      <Card>
        {notFound ? (
          <div className="px-6 py-12 text-center">
            <p className="font-medium">Lead introuvable</p>
            <Button asChild variant="outline" size="sm" className="mt-4"><Link to="/app/leads">Retour à la liste</Link></Button>
          </div>
        ) : (
          <ErrorState error={error} onRetry={() => void refetch()} />
        )}
      </Card>
    )
  }
  return <Content lead={data} />
}
