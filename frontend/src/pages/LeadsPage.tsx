import { Search, SearchX, X } from 'lucide-react'
import * as React from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { CrmBadge, DemoBadge, FollowupBadge, LeadStatusBadge, ReviewFlag, SegmentBadge } from '@/components/domain/badges'
import { PageHeader, Pagination } from '@/components/domain/misc'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/feedback'
import { Input, Select } from '@/components/ui/form-controls'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { useLeads } from '@/hooks/queries'
import { LEAD_STATUS, SERVICES, serviceLabel } from '@/lib/labels'
import { formatDateTime } from '@/lib/utils'
import type { LeadFilters, LeadStatus, Segment } from '@/types/api'

const PAGE_SIZE = 20

function useDebounced<T>(value: T, ms = 300) {
  const [v, setV] = React.useState(value)
  React.useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

export default function LeadsPage() {
  // Les filtres vivent dans l'URL : liens partageables, bouton « précédent » cohérent.
  const [params, setParams] = useSearchParams()
  const status = (params.get('status') ?? '') as LeadStatus | ''
  const segment = (params.get('segment') ?? '') as Segment | ''
  const service = params.get('service') ?? ''
  const page = Math.max(1, Number(params.get('page') ?? 1) || 1)
  const sort = (params.get('sort') ?? 'created_at') as NonNullable<LeadFilters['sort']>
  const order = (params.get('order') ?? 'desc') as 'asc' | 'desc'
  const [search, setSearch] = React.useState(params.get('q') ?? '')
  const q = useDebounced(search.trim())

  const update = React.useCallback(
    (patch: Record<string, string | null>) =>
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          for (const [k, v] of Object.entries(patch)) {
            if (v) next.set(k, v)
            else next.delete(k)
          }
          if (!('page' in patch)) next.delete('page')
          return next
        },
        { replace: true },
      ),
    [setParams],
  )

  React.useEffect(() => {
    if ((params.get('q') ?? '') !== q) update({ q: q || null })
  }, [q]) // eslint-disable-line react-hooks/exhaustive-deps

  const filters: LeadFilters = { status, segment, service: service || undefined, q: q || undefined, page, page_size: PAGE_SIZE, sort, order }
  const { data, isPending, isFetching, error, refetch } = useLeads(filters)
  const hasFilters = Boolean(status || segment || service || q)

  const toggleSort = (col: 'score' | 'created_at') =>
    update(sort === col ? { sort: col, order: order === 'desc' ? 'asc' : 'desc' } : { sort: col, order: 'desc' })
  const ariaSort = (col: string) => (sort === col ? (order === 'desc' ? 'descending' : 'ascending') : 'none')

  return (
    <div className="space-y-6">
      <PageHeader title="Leads" description="Toutes les demandes reçues, leur qualification et leur état de traitement." />

      <Card>
        <div className="flex flex-col gap-3 border-b p-4 lg:flex-row lg:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input
              type="search"
              placeholder="Rechercher un nom, un e-mail, une société…"
              aria-label="Rechercher un lead"
              className="pl-9"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:flex">
            <Select aria-label="Filtrer par statut" value={status} onChange={(e) => update({ status: e.target.value || null })} className="lg:w-44">
              <option value="">Tous les statuts</option>
              {(Object.keys(LEAD_STATUS) as LeadStatus[]).map((s) => (
                <option key={s} value={s}>{LEAD_STATUS[s].label}</option>
              ))}
            </Select>
            <Select aria-label="Filtrer par segment" value={segment} onChange={(e) => update({ segment: e.target.value || null })} className="lg:w-36">
              <option value="">Tous segments</option>
              <option value="HOT">HOT</option>
              <option value="WARM">WARM</option>
              <option value="COLD">COLD</option>
            </Select>
            <Select aria-label="Filtrer par service" value={service} onChange={(e) => update({ service: e.target.value || null })} className="col-span-2 sm:col-span-1 lg:w-56">
              <option value="">Tous les services</option>
              {SERVICES.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </Select>
            {hasFilters && (
              <Button
                variant="ghost"
                size="sm"
                className="col-span-2 sm:col-span-3 lg:col-auto"
                onClick={() => {
                  setSearch('')
                  setParams({}, { replace: true })
                }}
              >
                <X className="h-3.5 w-3.5" aria-hidden /> Réinitialiser
              </Button>
            )}
          </div>
        </div>

        {isPending ? (
          <div className="space-y-2 p-4" role="status" aria-label="Chargement des leads">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-12" />
            ))}
          </div>
        ) : error ? (
          <ErrorState error={error} onRetry={() => void refetch()} />
        ) : data.items.length === 0 ? (
          <EmptyState
            icon={hasFilters ? SearchX : undefined}
            title={hasFilters ? 'Aucun lead ne correspond à ces filtres' : 'Aucun lead pour l’instant'}
            description={hasFilters ? 'Modifiez ou réinitialisez les filtres.' : 'Les demandes soumises depuis la page de démo apparaîtront ici.'}
            action={
              hasFilters ? undefined : (
                <Button asChild variant="outline" size="sm" className="mt-2">
                  <Link to="/demo">Soumettre une demande</Link>
                </Button>
              )
            }
          />
        ) : (
          <>
            <div className={isFetching ? 'opacity-70 transition-opacity' : 'transition-opacity'}>
              <Table aria-label="Liste des leads">
                <THead>
                  <TR className="hover:bg-transparent">
                    <TH>Prospect</TH>
                    <TH>Service</TH>
                    <TH aria-sort={ariaSort('score')}>
                      <button type="button" className="inline-flex items-center gap-1 uppercase hover:text-foreground" onClick={() => toggleSort('score')}>
                        Score {sort === 'score' && (order === 'desc' ? '↓' : '↑')}
                      </button>
                    </TH>
                    <TH>Statut</TH>
                    <TH className="hidden xl:table-cell">CRM</TH>
                    <TH className="hidden xl:table-cell">Brouillon</TH>
                    <TH aria-sort={ariaSort('created_at')}>
                      <button type="button" className="inline-flex items-center gap-1 uppercase hover:text-foreground" onClick={() => toggleSort('created_at')}>
                        Reçu {sort === 'created_at' && (order === 'desc' ? '↓' : '↑')}
                      </button>
                    </TH>
                  </TR>
                </THead>
                <TBody>
                  {data.items.map((l) => (
                    <TR key={l.id}>
                      <TD>
                        <Link to={`/app/leads/${l.id}`} className="group block min-w-44">
                          <span className="flex items-center gap-2 font-medium group-hover:text-primary group-hover:underline">
                            {l.full_name} <DemoBadge show={l.is_demo} />
                          </span>
                          <span className="block text-xs text-muted-foreground">{l.company ?? l.email}</span>
                        </Link>
                      </TD>
                      <TD className="text-muted-foreground">{serviceLabel(l.service ?? l.requested_service)}</TD>
                      <TD>
                        {l.score !== null ? (
                          <span className="flex items-center gap-2">
                            <span className="w-8 text-right font-semibold tabular-nums">{l.score}</span>
                            <SegmentBadge segment={l.segment} />
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground">Non qualifié</span>
                        )}
                      </TD>
                      <TD>
                        <span className="flex flex-col items-start gap-1">
                          <LeadStatusBadge status={l.status} />
                          {l.human_review_required && l.status !== 'MANUAL_REVIEW' && <ReviewFlag />}
                        </span>
                      </TD>
                      <TD className="hidden xl:table-cell"><CrmBadge status={l.crm_status} /></TD>
                      <TD className="hidden xl:table-cell"><FollowupBadge status={l.followup_status} /></TD>
                      <TD className="whitespace-nowrap text-xs text-muted-foreground">{formatDateTime(l.created_at)}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </div>
            <Pagination page={data.page} pageSize={data.page_size} total={data.total} loading={isFetching} onPage={(p) => update({ page: String(p) })} />
          </>
        )}
      </Card>
    </div>
  )
}
