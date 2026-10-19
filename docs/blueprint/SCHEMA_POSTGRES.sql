-- Schéma initial PostgreSQL de référence : à convertir en migrations Alembic.
-- Conception indicative : NON exécutée contre une vraie instance, à valider par migrations/tests.
-- Données sensibles: limiter accès via FastAPI; ne jamais exposer de rôle DB admin dans React.

CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    email_normalized TEXT NOT NULL,
    company TEXT,
    phone TEXT,
    consent_status TEXT NOT NULL DEFAULT 'unknown'
       CHECK (consent_status IN ('unknown','granted','denied')),
    consent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (organization_id, email_normalized)
);

CREATE TABLE leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    contact_id UUID NOT NULL REFERENCES contacts(id),
    source TEXT NOT NULL DEFAULT 'website',
    requested_service TEXT,
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'NEW'
      CHECK (status IN ('NEW','PROCESSING','QUALIFIED','MANUAL_REVIEW','READY','FAILED','ARCHIVED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_leads_org_created ON leads (organization_id, created_at DESC);
CREATE INDEX idx_leads_org_status ON leads (organization_id, status);

CREATE TABLE intake_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    lead_id UUID NOT NULL REFERENCES leads(id),
    client_request_id UUID NOT NULL,
    request_body_hash TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'website',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (organization_id, client_request_id)
);

CREATE TABLE qualifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID NOT NULL REFERENCES leads(id),
    version INTEGER NOT NULL DEFAULT 1,
    intent TEXT NOT NULL,
    service TEXT,
    budget_amount NUMERIC(14, 2),
    budget_currency CHAR(3),
    timeline_days INTEGER,
    language TEXT,
    summary TEXT,
    score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
    segment TEXT NOT NULL CHECK (segment IN ('HOT','WARM','COLD')),
    score_explanation JSONB NOT NULL DEFAULT '{}'::jsonb,
    extracted_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    model_name TEXT,
    scoring_rule_version TEXT NOT NULL,
    human_review_required BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (lead_id, version)
);

CREATE TABLE crm_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    contact_id UUID NOT NULL REFERENCES contacts(id),
    provider TEXT NOT NULL DEFAULT 'hubspot',
    external_contact_id TEXT,
    sync_status TEXT NOT NULL DEFAULT 'PENDING'
      CHECK (sync_status IN ('PENDING','SYNCED','RETRYING','FAILED')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error_code TEXT,
    last_synced_at TIMESTAMPTZ,
    UNIQUE (organization_id, contact_id, provider),
    UNIQUE (organization_id, provider, external_contact_id)
);

CREATE TABLE followups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID NOT NULL REFERENCES leads(id),
    channel TEXT NOT NULL DEFAULT 'email',
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT'
      CHECK (status IN ('DRAFT','APPROVED','REJECTED','READY_TO_SEND','SENT','FAILED')),
    creation_event_id UUID UNIQUE,
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE automation_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID REFERENCES leads(id),
    correlation_id UUID NOT NULL,
    workflow_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'STARTED'
      CHECK (status IN ('STARTED','SUCCEEDED','RETRYING','FAILED','MANUAL_REVIEW')),
    attempt_count INTEGER NOT NULL DEFAULT 1,
    error_code TEXT,
    duration_ms INTEGER,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);
CREATE INDEX idx_runs_corr ON automation_runs (correlation_id);

CREATE TABLE outbox_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    lead_id UUID REFERENCES leads(id),
    event_type TEXT NOT NULL,
    dedupe_key TEXT NOT NULL UNIQUE,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'PENDING'
      CHECK (status IN ('PENDING','PROCESSING','DELIVERED','RETRYING','DEAD_LETTER')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at TIMESTAMPTZ
);
CREATE INDEX idx_outbox_due ON outbox_events (status, next_attempt_at);

CREATE TABLE audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    lead_id UUID REFERENCES leads(id),
    actor_type TEXT NOT NULL CHECK (actor_type IN ('system','user','service')),
    actor_ref TEXT,
    action TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_org_created ON audit_events (organization_id, created_at DESC);

-- À ajouter au fur et à mesure : mécanisme d'authentification/RBAC et politiques de rétention.
-- L'intégrité organisationnelle entre contact/lead doit être vérifiée par la couche métier
-- ou renforcée avec clés composées selon les exigences multi-tenant de la V2.
