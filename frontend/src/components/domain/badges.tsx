import {
  AlertOctagon,
  CheckCircle2,
  CircleDashed,
  Clock,
  Flame,
  Loader2,
  RefreshCw,
  Snowflake,
  Sun,
  XCircle,
} from 'lucide-react'
import type * as React from 'react'
import { Badge } from '@/components/ui/badge'
import { CRM_STATUS, FOLLOWUP_STATUS, LEAD_STATUS, OUTBOX_STATUS, RUN_STATUS, SEGMENT, type Tone } from '@/lib/labels'
import { cn } from '@/lib/utils'
import type { CrmSyncStatus, FollowupStatus, LeadStatus, OutboxStatus, RunStatus, Segment } from '@/types/api'

const toneIcon: Record<Tone, React.ElementType> = {
  neutral: CircleDashed,
  primary: CircleDashed,
  info: Loader2,
  success: CheckCircle2,
  warning: Clock,
  danger: XCircle,
}

function ToneBadge({ tone, label, spin = false }: { tone: Tone; label: string; spin?: boolean }) {
  const Icon = toneIcon[tone]
  return (
    <Badge tone={tone}>
      <Icon className={cn('h-3 w-3', spin && tone === 'info' && 'animate-spin')} aria-hidden />
      {label}
    </Badge>
  )
}

export const LeadStatusBadge = ({ status }: { status: LeadStatus }) => (
  <ToneBadge tone={LEAD_STATUS[status].tone} label={LEAD_STATUS[status].label} spin={status === 'PROCESSING'} />
)
export const CrmBadge = ({ status }: { status: CrmSyncStatus | null }) =>
  status ? <ToneBadge tone={CRM_STATUS[status].tone} label={CRM_STATUS[status].label} /> : <span className="text-xs text-muted-foreground">—</span>
export const FollowupBadge = ({ status }: { status: FollowupStatus | null }) =>
  status ? <ToneBadge tone={FOLLOWUP_STATUS[status].tone} label={FOLLOWUP_STATUS[status].label} /> : <span className="text-xs text-muted-foreground">—</span>
export const RunBadge = ({ status }: { status: RunStatus }) => (
  <ToneBadge tone={RUN_STATUS[status].tone} label={RUN_STATUS[status].label} spin={status === 'STARTED'} />
)
export const OutboxBadge = ({ status }: { status: OutboxStatus | null }) =>
  status ? <ToneBadge tone={OUTBOX_STATUS[status].tone} label={OUTBOX_STATUS[status].label} /> : <span className="text-xs text-muted-foreground">—</span>

const segmentStyle: Record<Segment, { icon: React.ElementType; cls: string }> = {
  HOT: { icon: Flame, cls: 'bg-danger-soft text-hot' },
  WARM: { icon: Sun, cls: 'bg-warning-soft text-warm' },
  COLD: { icon: Snowflake, cls: 'bg-info-soft text-cold' },
}

export function SegmentBadge({ segment, className }: { segment: Segment | null; className?: string }) {
  if (!segment) return <span className="text-xs text-muted-foreground">—</span>
  const { icon: Icon, cls } = segmentStyle[segment]
  return (
    <span
      title={SEGMENT[segment].hint}
      className={cn('inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold tracking-wide', cls, className)}
    >
      <Icon className="h-3 w-3" aria-hidden />
      {SEGMENT[segment].label}
    </span>
  )
}

export function DemoBadge({ show = true }: { show?: boolean }) {
  if (!show) return null
  return (
    <Badge tone="primary" title="Donnée de démonstration synthétique">
      DÉMO
    </Badge>
  )
}

export function ReviewFlag() {
  return (
    <Badge tone="warning">
      <AlertOctagon className="h-3 w-3" aria-hidden /> Revue humaine
    </Badge>
  )
}

export const RetryingIcon = RefreshCw
