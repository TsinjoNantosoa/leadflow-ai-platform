import { Check, History, Mail, MailX, Pencil, ShieldCheck, X } from 'lucide-react'
import * as React from 'react'
import { Link } from 'react-router-dom'
import { FollowupBadge, SegmentBadge } from '@/components/domain/badges'
import { PageHeader, Pagination } from '@/components/domain/misc'
import { Alert, EmptyState, ErrorState, Skeleton } from '@/components/ui/feedback'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input, Label, Textarea } from '@/components/ui/form-controls'
import {
  useApproveFollowup,
  useEditFollowup,
  useFollowupHistory,
  useFollowups,
  useRejectFollowup,
} from '@/hooks/queries'
import { auditLabel } from '@/lib/labels'
import { cn, formatDateTime, formatRelative } from '@/lib/utils'
import type { FollowupReviewItem } from '@/types/api'

type StatusFilter = 'DRAFT' | 'APPROVED' | 'REJECTED' | ''
const TABS: { value: StatusFilter; label: string }[] = [
  { value: 'DRAFT', label: 'À examiner' },
  { value: 'APPROVED', label: 'Approuvés' },
  { value: 'REJECTED', label: 'Rejetés' },
  { value: '', label: 'Tous' },
]

function HistoryList({ id }: { id: string }) {
  const { data, isPending } = useFollowupHistory(id)
  if (isPending) return <Skeleton className="h-16" />
  if (!data || data.length === 0) return <p className="text-xs text-muted-foreground">Aucune décision enregistrée.</p>
  return (
    <ul className="space-y-2" aria-label="Historique des décisions">
      {data.map((h) => (
        <li key={h.id} className="flex flex-wrap items-baseline gap-x-2 text-xs">
          <span className="font-medium">{auditLabel(h.action)}</span>
          <span className="text-muted-foreground">{h.actor_type === 'user' ? h.actor_ref : 'automatisation'}</span>
          <time className="ml-auto text-muted-foreground" dateTime={h.created_at}>{formatDateTime(h.created_at)}</time>
        </li>
      ))}
    </ul>
  )
}

function ReviewCard({ item }: { item: FollowupReviewItem }) {
  const editable = item.status === 'DRAFT'
  const [editing, setEditing] = React.useState(false)
  const [subject, setSubject] = React.useState(item.subject)
  const [body, setBody] = React.useState(item.body)
  const [rejectOpen, setRejectOpen] = React.useState(false)
  const [reason, setReason] = React.useState('')
  const [showHistory, setShowHistory] = React.useState(false)
  const approve = useApproveFollowup()
  const reject = useRejectFollowup()
  const edit = useEditFollowup()
  const dirty = subject !== item.subject || body !== item.body

  // Un brouillon modifié ailleurs (autre onglet, autre commercial) remplace la saisie locale non éditée.
  React.useEffect(() => {
    if (!editing) {
      setSubject(item.subject)
      setBody(item.body)
    }
  }, [item.subject, item.body, item.edit_version, editing])

  return (
    <Card className={cn(editable && 'border-warning/40')} data-testid="review-card">
      <CardContent className="space-y-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <Link to={`/app/leads/${item.lead_id}`} className="font-semibold hover:text-primary hover:underline">
              {item.lead_full_name}
            </Link>
            <p className="text-xs text-muted-foreground">
              {item.lead_company ?? '—'} · brouillon {formatRelative(item.created_at)} · {item.llm_provider ?? '—'} / {item.model_name ?? '—'}
              {item.edit_version > 1 && ` · modifié ${item.edit_version - 1} fois`}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <SegmentBadge segment={item.lead_segment} />
            <FollowupBadge status={item.status} />
          </div>
        </div>

        {editing ? (
          <div className="space-y-3">
            <div>
              <Label htmlFor={`subject-${item.id}`}>Objet</Label>
              <Input id={`subject-${item.id}`} className="mt-1.5" value={subject} maxLength={200} onChange={(e) => setSubject(e.target.value)} />
            </div>
            <div>
              <Label htmlFor={`body-${item.id}`}>Message</Label>
              <Textarea id={`body-${item.id}`} className="mt-1.5 min-h-56 font-sans" value={body} onChange={(e) => setBody(e.target.value)} />
              <p className="mt-1 text-xs text-muted-foreground">{body.length} / 6000 caractères</p>
            </div>
          </div>
        ) : (
          <div className="rounded-lg border bg-muted/40 p-4">
            <p className="mb-2 text-sm font-medium">Objet : {item.subject}</p>
            <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">{item.body}</p>
          </div>
        )}

        {item.status === 'APPROVED' && (
          <p className="flex items-center gap-2 text-xs text-success">
            <ShieldCheck className="h-4 w-4" aria-hidden /> Approuvé par {item.approved_by} le {formatDateTime(item.approved_at)} — <strong>aucun e-mail n’a été envoyé.</strong>
          </p>
        )}
        {item.status === 'REJECTED' && (
          <p className="flex items-start gap-2 text-xs text-danger">
            <MailX className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> Rejeté par {item.rejected_by} le {formatDateTime(item.rejected_at)}
            {item.reject_reason && <> — « {item.reject_reason} »</>}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-2">
          {editable && !editing && (
            <Button variant="outline" size="sm" onClick={() => setEditing(true)}><Pencil className="h-3.5 w-3.5" aria-hidden /> Modifier</Button>
          )}
          {editing && (
            <>
              <Button
                size="sm"
                loading={edit.isPending}
                disabled={!dirty || subject.trim().length < 3 || body.trim().length < 20}
                onClick={() =>
                  edit.mutate({ id: item.id, subject: subject.trim(), body: body.trim(), version: item.edit_version }, { onSuccess: () => setEditing(false) })
                }
              >
                Enregistrer
              </Button>
              <Button variant="ghost" size="sm" onClick={() => { setEditing(false); setSubject(item.subject); setBody(item.body) }}>Annuler</Button>
            </>
          )}
          {editable && !editing && (
            <>
              <Button variant="success" size="sm" loading={approve.isPending} onClick={() => approve.mutate({ id: item.id, version: item.edit_version })}>
                <Check className="h-3.5 w-3.5" aria-hidden /> Approuver
              </Button>
              <Button variant="outline" size="sm" onClick={() => setRejectOpen(true)}><X className="h-3.5 w-3.5" aria-hidden /> Rejeter</Button>
            </>
          )}
          <Button variant="ghost" size="sm" className="ml-auto" onClick={() => setShowHistory((s) => !s)} aria-expanded={showHistory}>
            <History className="h-3.5 w-3.5" aria-hidden /> Historique
          </Button>
        </div>

        {showHistory && <div className="border-t pt-3"><HistoryList id={item.id} /></div>}
      </CardContent>

      <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rejeter ce brouillon ?</DialogTitle>
            <DialogDescription>La décision est enregistrée dans l’historique. Aucun e-mail n’est concerné : rien n’a été envoyé.</DialogDescription>
          </DialogHeader>
          <div>
            <Label htmlFor={`reason-${item.id}`}>Raison (facultatif)</Label>
            <Textarea id={`reason-${item.id}`} className="mt-1.5 min-h-20" value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setRejectOpen(false)}>Annuler</Button>
            <Button
              variant="destructive"
              loading={reject.isPending}
              onClick={() => reject.mutate({ id: item.id, reason: reason.trim() || undefined }, { onSuccess: () => setRejectOpen(false) })}
            >
              Confirmer le rejet
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}

export default function ReviewsPage() {
  const [status, setStatus] = React.useState<StatusFilter>('DRAFT')
  const [page, setPage] = React.useState(1)
  const { data, isPending, isFetching, error, refetch } = useFollowups({ status, page })

  return (
    <div className="space-y-6">
      <PageHeader title="Revue humaine" description="Relisez, corrigez puis approuvez ou rejetez les brouillons de réponse préparés par l’IA." />
      <Alert tone="info" title="Approuver ne déclenche aucun envoi">
        Cette version ne contient aucune fonction d’envoi d’e-mail : l’approbation est uniquement une décision interne tracée.
      </Alert>

      <div role="tablist" aria-label="Filtrer les brouillons" className="inline-flex flex-wrap gap-1 rounded-lg bg-muted p-1">
        {TABS.map((t) => (
          <button
            key={t.label}
            role="tab"
            type="button"
            aria-selected={status === t.value}
            onClick={() => { setStatus(t.value); setPage(1) }}
            className={cn(
              'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
              status === t.value ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {isPending ? (
        <div className="space-y-3" role="status" aria-label="Chargement des brouillons">
          <Skeleton className="h-56" />
          <Skeleton className="h-56" />
        </div>
      ) : error ? (
        <Card><ErrorState error={error} onRetry={() => void refetch()} /></Card>
      ) : data.items.length === 0 ? (
        <Card>
          <EmptyState icon={Mail} title={status === 'DRAFT' ? 'Aucun brouillon à examiner' : 'Aucun brouillon dans cette catégorie'}
            description="Les brouillons apparaissent ici après la qualification d’un lead." />
        </Card>
      ) : (
        <div className={cn('space-y-4', isFetching && 'opacity-80 transition-opacity')}>
          {data.items.map((f) => <ReviewCard key={f.id} item={f} />)}
          <Card><Pagination page={data.page} pageSize={data.page_size} total={data.total} loading={isFetching} onPage={setPage} /></Card>
        </div>
      )}
    </div>
  )
}
