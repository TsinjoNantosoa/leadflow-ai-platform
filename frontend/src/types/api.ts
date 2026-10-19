// Types miroirs des schémas Pydantic du backend (backend/app/schemas/dashboard.py). Source de vérité : /openapi.json.

export type Role = 'ADMIN' | 'SALES'
export type LeadStatus = 'NEW' | 'PROCESSING' | 'QUALIFIED' | 'MANUAL_REVIEW' | 'READY' | 'FAILED' | 'ARCHIVED'
export type Segment = 'HOT' | 'WARM' | 'COLD'
export type CrmSyncStatus = 'PENDING' | 'SYNCED' | 'RETRYING' | 'FAILED'
export type FollowupStatus = 'DRAFT' | 'APPROVED' | 'REJECTED'
export type RunStatus = 'STARTED' | 'SUCCEEDED' | 'RETRYING' | 'FAILED' | 'MANUAL_REVIEW'
export type OutboxStatus = 'PENDING' | 'PROCESSING' | 'DELIVERED' | 'RETRYING' | 'DEAD_LETTER'
export type TimelineState = 'done' | 'pending' | 'failed' | 'skipped' | 'attention' | 'in_progress'

export interface User {
  id: string
  email: string
  full_name: string
  role: Role
}
export interface SessionInfo {
  user: User
  csrf_token: string
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface LeadListItem {
  id: string
  created_at: string
  status: LeadStatus
  status_reason: string | null
  full_name: string
  email: string
  company: string | null
  requested_service: string | null
  service: string | null
  score: number | null
  segment: Segment | null
  human_review_required: boolean
  crm_status: CrmSyncStatus | null
  followup_status: FollowupStatus | null
  is_demo: boolean
}

export interface ScoreFactor {
  id: string
  label: string
  max_points: number
  points: number
  awarded: boolean
  detail: string
}
export interface ScoreExplanation {
  rule_version: string
  total: number
  segment: Segment
  thresholds: { HOT: number; WARM: number }
  factors: ScoreFactor[]
  inputs_used: Record<string, unknown>
}
export interface Qualification {
  id: string
  version: number
  intent: string
  service: string | null
  budget_amount: string | number | null
  budget_currency: string | null
  timeline_days: number | null
  language: string | null
  summary: string | null
  need_clarity: string | null
  score: number
  segment: Segment
  score_explanation: ScoreExplanation
  extracted_data: { evidence?: string[] } & Record<string, unknown>
  llm_provider: string | null
  model_name: string | null
  prompt_version: string | null
  scoring_rule_version: string
  human_review_required: boolean
  review_reasons: string[]
  created_at: string
}

export interface Followup {
  id: string
  lead_id: string
  channel: string
  subject: string
  body: string
  language: string | null
  status: FollowupStatus
  edit_version: number
  model_name: string | null
  prompt_version: string | null
  llm_provider: string | null
  edited_by: string | null
  edited_at: string | null
  approved_by: string | null
  approved_at: string | null
  rejected_by: string | null
  rejected_at: string | null
  reject_reason: string | null
  created_at: string
  updated_at: string
  is_demo: boolean
}
export interface FollowupReviewItem extends Followup {
  lead_full_name: string
  lead_company: string | null
  lead_score: number | null
  lead_segment: Segment | null
}

export interface Run {
  id: string
  lead_id: string | null
  outbox_event_id: string | null
  correlation_id: string
  workflow_name: string
  event_type: string | null
  status: RunStatus
  attempt_count: number
  max_attempts: number | null
  error_code: string | null
  error_message: string | null
  duration_ms: number | null
  started_at: string
  finished_at: string | null
  event_status: OutboxStatus | null
  next_attempt_at: string | null
  can_retry: boolean
  is_demo: boolean
}

export interface AuditEvent {
  id: string
  action: string
  actor_type: 'system' | 'user' | 'service'
  actor_ref: string | null
  metadata: Record<string, unknown>
  created_at: string
}

export interface TimelineStep {
  key: string
  label: string
  state: TimelineState
  at: string | null
  detail: string | null
}

export interface LeadDetail {
  id: string
  created_at: string
  status: LeadStatus
  status_reason: string | null
  source: string
  requested_service: string | null
  message: string
  is_demo: boolean
  privacy_notice_version: string | null
  contact: {
    id: string
    full_name: string
    email: string
    company: string | null
    phone: string | null
    consent_status: string
    lead_count: number
  }
  qualification: Qualification | null
  qualification_history: { version: number; score: number; segment: Segment; created_at: string; human_review_required: boolean }[]
  crm: {
    provider: string
    external_contact_id: string | null
    sync_status: CrmSyncStatus
    attempt_count: number
    last_error_code: string | null
    last_synced_at: string | null
  } | null
  followups: Followup[]
  runs: Run[]
  audit: AuditEvent[]
  timeline: TimelineStep[]
}

export interface Overview {
  generated_at: string
  data_origin: { total_leads: number; demo_leads: number; real_leads: number }
  leads: {
    received: number
    qualified: number
    manual_review: number
    failed: number
    in_progress: number
    by_status: Record<string, number>
  }
  segments: Record<Segment, number>
  series: { date: string; count: number }[]
  runs_last_7_days: Record<string, Partial<Record<RunStatus, number>>>
  outbox: Partial<Record<OutboxStatus, number>>
  drafts: Partial<Record<FollowupStatus, number>>
  crm: Partial<Record<CrmSyncStatus, number>>
  qualification_latency_seconds: { samples: number; p50: number | null; p95: number | null; scope: string }
  llm_usage: { calls: number; input_tokens: number; output_tokens: number; estimated_cost_usd: number | null; scope: string }
  recent_activity: {
    id: string
    action: string
    actor_type: string
    lead_id: string | null
    lead_name: string | null
    created_at: string
    is_demo: boolean
  }[]
}

export interface LeadReceipt {
  lead_id: string
  status: string
  request_id: string
}

export interface LeadFilters {
  status?: LeadStatus | ''
  segment?: Segment | ''
  service?: string
  q?: string
  review?: boolean
  page?: number
  page_size?: number
  sort?: 'created_at' | 'score' | 'status' | 'name'
  order?: 'asc' | 'desc'
}
