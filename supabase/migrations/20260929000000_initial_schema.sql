-- ============================================================================
-- 1. TENANTS & USER PROFILES
-- ============================================================================
CREATE TABLE user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    full_name TEXT,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    briefing_format_preference TEXT NOT NULL DEFAULT 'standard'
        CHECK (briefing_format_preference IN ('standard', 'concise', 'detailed')),
    prep_lead_time_hours INTEGER NOT NULL DEFAULT 2
        CHECK (prep_lead_time_hours BETWEEN 1 AND 72),
    hindsight_bank_id TEXT UNIQUE,
    monthly_budget_usd NUMERIC(6, 2) NOT NULL DEFAULT 25.00
        CHECK (monthly_budget_usd >= 5.00),
    current_month_spend_usd NUMERIC(8, 4) NOT NULL DEFAULT 0.0000
        CHECK (current_month_spend_usd >= 0.0000),
    billing_cycle_anchor_day INTEGER NOT NULL DEFAULT 1
        CHECK (billing_cycle_anchor_day BETWEEN 1 AND 28),
    account_status TEXT NOT NULL DEFAULT 'active'
        CHECK (account_status IN ('active', 'deleting', 'suspended')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_user_profiles_id_user UNIQUE (id)
);

-- ============================================================================
-- 2. PROJECTS & CONTACTS
-- ============================================================================
CREATE TABLE projects (
    id UUID DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived', 'completed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT fk_projects_user FOREIGN KEY (user_id) REFERENCES user_profiles(id) ON DELETE CASCADE,
    CONSTRAINT uq_projects_id_user UNIQUE (id, user_id)
);

CREATE TABLE contacts (
    id UUID DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    name TEXT NOT NULL,
    email TEXT,
    organization TEXT,
    role_title TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT fk_contacts_user FOREIGN KEY (user_id) REFERENCES user_profiles(id) ON DELETE CASCADE,
    CONSTRAINT uq_contacts_id_user UNIQUE (id, user_id)
);

-- ============================================================================
-- 3. MEETINGS & PARTICIPANTS (With Column-Specific SET NULL)
-- ============================================================================
CREATE TABLE meetings (
    id UUID DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    project_id UUID,
    title TEXT NOT NULL,
    purpose TEXT,
    meeting_timezone TEXT NOT NULL DEFAULT 'UTC',
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled'
        CHECK (status IN ('scheduled', 'preparing', 'prepared', 'completed', 'cancelled')),
    user_importance_override TEXT
        CHECK (user_importance_override IN ('low', 'medium', 'high', 'critical')),
    effective_importance TEXT NOT NULL DEFAULT 'medium'
        CHECK (effective_importance IN ('low', 'medium', 'high', 'critical')),
    meeting_version INTEGER NOT NULL DEFAULT 1,
    active_prep_job_id UUID,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT chk_meeting_times CHECK (end_time > start_time),
    CONSTRAINT fk_meetings_user FOREIGN KEY (user_id) REFERENCES user_profiles(id) ON DELETE CASCADE,
    CONSTRAINT fk_meetings_project FOREIGN KEY (project_id, user_id) 
        REFERENCES projects(id, user_id) ON DELETE SET NULL (project_id),
    CONSTRAINT uq_meetings_id_user UNIQUE (id, user_id)
);

CREATE TABLE meeting_participants (
    id UUID DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    meeting_id UUID NOT NULL,
    contact_id UUID,
    name TEXT NOT NULL,
    role TEXT,
    is_organizer BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (id),
    CONSTRAINT fk_participants_meeting FOREIGN KEY (meeting_id, user_id) 
        REFERENCES meetings(id, user_id) ON DELETE CASCADE,
    CONSTRAINT fk_participants_contact FOREIGN KEY (contact_id, user_id) 
        REFERENCES contacts(id, user_id) ON DELETE SET NULL (contact_id),
    CONSTRAINT uq_participants_meeting_contact UNIQUE (meeting_id, contact_id)
);

-- ============================================================================
-- 4. DOCUMENTS & EXTRACTION
-- ============================================================================
CREATE TABLE documents (
    id UUID DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    meeting_id UUID,
    project_id UUID,
    filename TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    file_type TEXT NOT NULL CHECK (file_type IN ('pdf', 'docx', 'txt', 'md')),
    file_size_bytes BIGINT NOT NULL CHECK (file_size_bytes <= 26214400), -- 25MB max
    sha256_checksum TEXT NOT NULL,
    source_version INTEGER NOT NULL DEFAULT 1,
    processing_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (processing_status IN ('pending', 'extracted', 'failed')),
    extracted_text_storage_path TEXT,
    inline_extracted_text TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT fk_documents_meeting FOREIGN KEY (meeting_id, user_id) 
        REFERENCES meetings(id, user_id) ON DELETE SET NULL (meeting_id),
    CONSTRAINT fk_documents_project FOREIGN KEY (project_id, user_id) 
        REFERENCES projects(id, user_id) ON DELETE SET NULL (project_id),
    CONSTRAINT uq_documents_id_user UNIQUE (id, user_id)
);

-- ============================================================================
-- 5. BRIEFINGS & VALIDATED EVIDENCE
-- ============================================================================
CREATE TABLE briefings (
    id UUID DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    meeting_id UUID NOT NULL,
    meeting_version INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'ready'
        CHECK (status IN ('ready', 'partial', 'degraded')),
    summary TEXT NOT NULL,
    talking_points JSONB NOT NULL DEFAULT '[]',
    identified_risks JSONB NOT NULL DEFAULT '[]',
    strategic_questions JSONB NOT NULL DEFAULT '[]',
    assumptions_and_gaps JSONB NOT NULL DEFAULT '[]',
    conflicts_detected JSONB NOT NULL DEFAULT '[]',
    model_provider TEXT NOT NULL,
    model_name TEXT NOT NULL,
    is_latest BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT fk_briefings_meeting FOREIGN KEY (meeting_id, user_id) 
        REFERENCES meetings(id, user_id) ON DELETE CASCADE,
    CONSTRAINT uq_briefings_id_user UNIQUE (id, user_id)
);

CREATE UNIQUE INDEX idx_briefings_single_latest 
    ON briefings (meeting_id) 
    WHERE (is_latest = TRUE);

CREATE TABLE evidence_items (
    id UUID DEFAULT gen_random_uuid(),
    briefing_id UUID NOT NULL,
    user_id UUID NOT NULL,
    claim_text TEXT NOT NULL,
    epistemic_class TEXT NOT NULL 
        CHECK (epistemic_class IN ('direct_fact', 'user_confirmed', 'model_inference', 'unverified_assumption')),
    source_type TEXT NOT NULL 
        CHECK (source_type IN ('document', 'contact_note', 'previous_meeting', 'user_profile')),
    source_id UUID,
    source_version INTEGER NOT NULL DEFAULT 1,
    chunk_id TEXT,
    chunk_index INTEGER,
    excerpt TEXT NOT NULL,
    source_location TEXT, -- e.g., "Page 3, Paragraph 2"
    verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT fk_evidence_briefing FOREIGN KEY (briefing_id, user_id) 
        REFERENCES briefings(id, user_id) ON DELETE CASCADE
);

-- ============================================================================
-- 6. COMMITMENTS & RECOMMENDATIONS
-- ============================================================================
CREATE TABLE commitments (
    id UUID DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    meeting_id UUID,
    project_id UUID,
    owner_name TEXT NOT NULL,
    description TEXT NOT NULL,
    due_date DATE,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'in_progress', 'completed', 'missed', 'cancelled')),
    is_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    source_excerpt TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT fk_commitments_meeting FOREIGN KEY (meeting_id, user_id) 
        REFERENCES meetings(id, user_id) ON DELETE SET NULL (meeting_id),
    CONSTRAINT fk_commitments_project FOREIGN KEY (project_id, user_id) 
        REFERENCES projects(id, user_id) ON DELETE SET NULL (project_id),
    CONSTRAINT uq_commitments_id_user UNIQUE (id, user_id)
);

CREATE TABLE recommendations (
    id UUID DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    meeting_id UUID NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('risk', 'preparation', 'followup', 'relationship')),
    title TEXT NOT NULL,
    rationale TEXT NOT NULL,
    evidence_references JSONB NOT NULL DEFAULT '[]',
    priority TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'dismissed', 'acted_upon')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT fk_recommendations_meeting FOREIGN KEY (meeting_id, user_id) 
        REFERENCES meetings(id, user_id) ON DELETE CASCADE
);

-- ============================================================================
-- 7. PREFERENCE LEARNING ENGINE
-- ============================================================================
CREATE TABLE preferences (
    id UUID DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    dimension TEXT NOT NULL CHECK (dimension IN ('briefing_format', 'topic_priority', 'preparation_timing')),
    scope TEXT NOT NULL CHECK (scope IN ('global', 'meeting_type', 'project', 'contact')),
    scope_id TEXT NOT NULL DEFAULT '',
    key TEXT NOT NULL,
    value JSONB NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'learned' CHECK (source_type IN ('explicit', 'learned')),
    confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.500 CHECK (confidence BETWEEN 0.000 AND 1.000),
    state TEXT NOT NULL DEFAULT 'candidate' 
        CHECK (state IN ('candidate', 'tentative', 'active', 'conflicted', 'dormant', 'rejected')),
    last_reinforced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT fk_preferences_user FOREIGN KEY (user_id) REFERENCES user_profiles(id) ON DELETE CASCADE,
    CONSTRAINT uq_preferences_scope UNIQUE (user_id, dimension, scope, scope_id, key),
    CONSTRAINT uq_preferences_id_user UNIQUE (id, user_id)
);

CREATE TABLE learning_observations (
    id UUID DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    preference_id UUID NOT NULL,
    signal_type TEXT NOT NULL,
    weight NUMERIC(4, 3) NOT NULL CHECK (weight BETWEEN -1.000 AND 1.000),
    metadata JSONB NOT NULL DEFAULT '{}',
    is_reversed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT fk_observations_pref FOREIGN KEY (preference_id, user_id) 
        REFERENCES preferences(id, user_id) ON DELETE CASCADE
);

-- ============================================================================
-- 8. TRANSACTIONAL LEASED JOB QUEUE
-- ============================================================================
CREATE TABLE background_jobs (
    id UUID DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    job_type TEXT NOT NULL 
        CHECK (job_type IN ('prep_meeting', 'refresh_briefing', 'parse_document', 'extract_outcomes', 'memory_sync')),
    resource_id UUID NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    payload JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'completed', 'failed', 'dead_letter', 'superseded', 'cancelled')),
    priority INTEGER NOT NULL DEFAULT 10,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    scheduled_for TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    locked_at TIMESTAMPTZ,
    locked_by TEXT,
    heartbeat_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    next_retry_at TIMESTAMPTZ,
    superseded_by_job_id UUID REFERENCES background_jobs(id),
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT fk_jobs_user FOREIGN KEY (user_id) REFERENCES user_profiles(id) ON DELETE CASCADE
);

CREATE INDEX idx_jobs_claimable ON background_jobs (priority, scheduled_for)
    WHERE status = 'queued';

CREATE INDEX idx_jobs_leases ON background_jobs (lease_expires_at)
    WHERE status = 'running';

-- ============================================================================
-- 9. ATOMIC USAGE & COST LEDGER
-- ============================================================================
CREATE TABLE llm_usage_ledger (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    job_id UUID REFERENCES background_jobs(id) ON DELETE SET NULL,
    request_id TEXT NOT NULL,
    operation_type TEXT NOT NULL CHECK (operation_type IN ('briefing', 'document_map', 'document_reduce', 'outcome_proposal', 'chat')),
    model_provider TEXT NOT NULL,
    model_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'reserved' CHECK (status IN ('reserved', 'settled', 'released')),
    reserved_cost_usd NUMERIC(8, 4) NOT NULL,
    actual_cost_usd NUMERIC(8, 4),
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    settled_at TIMESTAMPTZ
);

-- ============================================================================
-- 10. AUDIT EVENTS
-- ============================================================================
CREATE TABLE audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID,
    original_user_hash TEXT NOT NULL,
    event_type TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id UUID NOT NULL,
    ip_address TEXT,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_audit_user FOREIGN KEY (user_id) REFERENCES user_profiles(id) ON DELETE SET NULL
);

-- ============================================================================
-- 11. ROW-LEVEL SECURITY (RLS) POLICIES
-- ============================================================================
-- Enable RLS on all tenant-owned tables
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE meetings ENABLE ROW LEVEL SECURITY;
ALTER TABLE meeting_participants ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE briefings ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE commitments ENABLE ROW LEVEL SECURITY;
ALTER TABLE recommendations ENABLE ROW LEVEL SECURITY;
ALTER TABLE preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE learning_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE background_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE llm_usage_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;

-- Helper to apply RLS policy to all tables securely relying on the JWT claim
-- In our FastAPI backend connection manager, we will SET LOCAL "request.jwt.claim.sub" = '<uuid>'
DO $$
DECLARE
    t_name text;
BEGIN
    FOR t_name IN (
        SELECT tablename 
        FROM pg_tables 
        WHERE schemaname = 'public' 
          AND tablename NOT IN ('schema_migrations')
    ) LOOP
        IF t_name = 'user_profiles' THEN
            EXECUTE format('
                CREATE POLICY tenant_isolation_policy ON %I 
                FOR ALL 
                USING (id::text = current_setting(''request.jwt.claim.sub'', true))
                WITH CHECK (id::text = current_setting(''request.jwt.claim.sub'', true));
            ', t_name);
        ELSE
            EXECUTE format('
                CREATE POLICY tenant_isolation_policy ON %I 
                FOR ALL 
                USING (user_id::text = current_setting(''request.jwt.claim.sub'', true))
                WITH CHECK (user_id::text = current_setting(''request.jwt.claim.sub'', true));
            ', t_name);
        END IF;
    END LOOP;
END
$$;
