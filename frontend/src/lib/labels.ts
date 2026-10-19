import type { CrmSyncStatus, FollowupStatus, LeadStatus, OutboxStatus, RunStatus, Segment } from '@/types/api'

export const SERVICES: { value: string; label: string }[] = [
  { value: 'web_development', label: 'Création de site web' },
  { value: 'workflow_automation', label: 'Automatisation de processus' },
  { value: 'customer_support_automation', label: 'Automatisation du support client' },
  { value: 'ai_integration', label: "Intégration d'IA" },
  { value: 'data_dashboard', label: 'Tableaux de bord de données' },
  { value: 'other', label: 'Autre besoin' },
]
export const serviceLabel = (v: string | null | undefined) =>
  v ? (SERVICES.find((s) => s.value === v)?.label ?? (v === 'unknown' ? 'Non identifié' : v)) : '—'

export const LEAD_STATUS: Record<LeadStatus, { label: string; tone: Tone }> = {
  NEW: { label: 'Nouveau', tone: 'info' },
  PROCESSING: { label: 'En traitement', tone: 'info' },
  QUALIFIED: { label: 'Qualifié', tone: 'success' },
  MANUAL_REVIEW: { label: 'À examiner', tone: 'warning' },
  READY: { label: 'Prêt', tone: 'success' },
  FAILED: { label: 'Échec', tone: 'danger' },
  ARCHIVED: { label: 'Archivé', tone: 'neutral' },
}

export const SEGMENT: Record<Segment, { label: string; hint: string }> = {
  HOT: { label: 'HOT', hint: 'Score ≥ 75' },
  WARM: { label: 'WARM', hint: 'Score 45–74' },
  COLD: { label: 'COLD', hint: 'Score < 45' },
}

export const CRM_STATUS: Record<CrmSyncStatus, { label: string; tone: Tone }> = {
  PENDING: { label: 'En attente', tone: 'neutral' },
  SYNCED: { label: 'Synchronisé', tone: 'success' },
  RETRYING: { label: 'Nouvelle tentative', tone: 'warning' },
  FAILED: { label: 'Échec', tone: 'danger' },
}

export const FOLLOWUP_STATUS: Record<FollowupStatus, { label: string; tone: Tone }> = {
  DRAFT: { label: 'Brouillon', tone: 'warning' },
  APPROVED: { label: 'Approuvé', tone: 'success' },
  REJECTED: { label: 'Rejeté', tone: 'danger' },
}

export const RUN_STATUS: Record<RunStatus, { label: string; tone: Tone }> = {
  STARTED: { label: 'En cours', tone: 'info' },
  SUCCEEDED: { label: 'Réussi', tone: 'success' },
  RETRYING: { label: 'Nouvelle tentative', tone: 'warning' },
  FAILED: { label: 'Échec', tone: 'danger' },
  MANUAL_REVIEW: { label: 'Revue manuelle', tone: 'warning' },
}

export const OUTBOX_STATUS: Record<OutboxStatus, { label: string; tone: Tone }> = {
  PENDING: { label: 'En file', tone: 'neutral' },
  PROCESSING: { label: 'Réservé', tone: 'info' },
  DELIVERED: { label: 'Livré', tone: 'success' },
  RETRYING: { label: 'Retry planifié', tone: 'warning' },
  DEAD_LETTER: { label: 'Dead-letter', tone: 'danger' },
}

export const WORKFLOW_LABEL: Record<string, string> = {
  'LF-WF-01-Lead-Qualification': 'Qualification',
  'LF-WF-02-HubSpot-CRM-Sync': 'Synchronisation CRM',
  'LF-WF-03-Followup-Draft': 'Brouillon de suivi',
  'LF-WF-04-Operations-Recovery': 'Opérations',
}

export const AUDIT_LABEL: Record<string, string> = {
  'lead.received': 'Demande reçue',
  'lead.validated': 'Demande validée',
  'lead.status_changed': 'Statut modifié',
  'lead.qualified': 'Lead qualifié',
  'lead.manual_review_required': 'Revue manuelle requise',
  'lead.retry_requested': 'Relance demandée',
  'lead.invalid_transition': 'Transition refusée',
  'ai.extraction_completed': 'Extraction IA terminée',
  'crm.synced': 'CRM synchronisé',
  'crm.sync_failed': 'Échec de synchronisation CRM',
  'crm.external_id_conflict': 'Conflit d’identifiant CRM',
  'draft.created': 'Brouillon créé',
  'draft.edited': 'Brouillon modifié',
  'draft.approved': 'Brouillon approuvé',
  'draft.rejected': 'Brouillon rejeté',
  'draft.skipped': 'Brouillon non généré',
  'draft.policy_violation': 'Brouillon refusé par la politique',
  'automation.dead_letter': 'Abandon après échecs répétés',
  'automation.manual_retry': 'Reprise manuelle',
  'automation.note': 'Note d’automatisation',
  'intake.idempotency_conflict': 'Conflit d’idempotence',
  'privacy.contact_erased': 'Données du contact effacées',
}
export const auditLabel = (action: string) => AUDIT_LABEL[action] ?? action

export const REVIEW_REASON: Record<string, string> = {
  llm_flagged_review: 'Le modèle a signalé une ambiguïté',
  prompt_injection_suspected: "Tentative d'instruction détectée dans le message",
  evidence_not_found_in_message: 'Citations non retrouvées dans le message',
  budget_not_found_in_message: 'Budget non retrouvé dans le message (écarté)',
  need_unclear: 'Besoin peu clair',
  clear_need_without_evidence: 'Besoin jugé clair sans preuve',
  LLM_INVALID_OUTPUT: 'Sortie du modèle invalide',
  LLM_REFUSAL: 'Refus du modèle',
  EXTRACTION_INVALID_AT_WORKFLOW: 'Extraction incomplète',
}
export const reviewReason = (code: string) => REVIEW_REASON[code] ?? code

export type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'danger' | 'primary'
