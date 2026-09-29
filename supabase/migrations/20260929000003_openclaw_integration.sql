-- =============================================================================
-- Meeting 7: OpenClaw Integration & Automated Information Gathering
-- Adds: meeting_integrations, meeting_attendance_sessions, transcript_sources,
--       transcript_segments, information_gathering_runs, research_sources,
--       integration_sync_state
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. MEETING INTEGRATIONS (per-meeting platform auth + attendance config)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.meeting_integrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    integration_type TEXT NOT NULL,  -- 'google_meet', 'microsoft_teams', 'zoom', 'openclaw'
    attendance_mode TEXT NOT NULL DEFAULT 'disabled',  -- 'disabled', 'manual', 'automatic'
    is_enabled BOOLEAN NOT NULL DEFAULT false,
    -- Scope and authorization
    oauth_token_encrypted TEXT,  -- AES-encrypted, never log
    refresh_token_encrypted TEXT,
    token_expires_at TIMESTAMPTZ,
    scopes TEXT[],
    -- Attendance rules (JSONB for flexibility)
    attendance_rules JSONB NOT NULL DEFAULT '{}',
    -- Allowed meeting types: internal, external, all
    allowed_meeting_types TEXT[] NOT NULL DEFAULT '{}'::TEXT[],
    -- Platforms eligible for auto-join
    eligible_platforms TEXT[] NOT NULL DEFAULT '{}'::TEXT[],
    -- Auto-join window (minutes before start)
    join_before_minutes INT NOT NULL DEFAULT 2,
    auto_leave_on_end BOOLEAN NOT NULL DEFAULT true,
    transcript_capture_enabled BOOLEAN NOT NULL DEFAULT false,
    -- Sync state
    last_sync_at TIMESTAMPTZ,
    sync_cursor TEXT,  -- incremental sync token
    health_status TEXT NOT NULL DEFAULT 'unknown',  -- 'healthy', 'degraded', 'error', 'revoked', 'unknown'
    health_last_checked_at TIMESTAMPTZ,
    health_error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_mi_user FOREIGN KEY (user_id) REFERENCES public.user_profiles(id) ON DELETE CASCADE,
    CONSTRAINT uq_mi_user_type UNIQUE (user_id, integration_type),
    CONSTRAINT chk_attendance_mode CHECK (attendance_mode IN ('disabled', 'manual', 'automatic')),
    CONSTRAINT chk_health_status CHECK (health_status IN ('healthy', 'degraded', 'error', 'revoked', 'unknown'))
);

ALTER TABLE public.meeting_integrations ENABLE ROW LEVEL SECURITY;
CREATE POLICY mi_tenant_isolation ON public.meeting_integrations
    FOR ALL
    USING (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
    WITH CHECK (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid);
GRANT ALL ON TABLE public.meeting_integrations TO agent_app_user, authenticated;

-- -----------------------------------------------------------------------------
-- 2. MEETING ATTENDANCE SESSIONS (state machine per meeting per join attempt)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.meeting_attendance_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    meeting_id UUID NOT NULL,
    meeting_version INT NOT NULL DEFAULT 1,  -- anti-stale guard
    background_job_id UUID,
    -- State machine
    status TEXT NOT NULL DEFAULT 'scheduled',
    -- scheduled, eligible, joining, waiting_for_admission, joined,
    -- capturing, completed, failed, cancelled, consent_required
    -- Timestamps
    scheduled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    eligible_at TIMESTAMPTZ,
    join_requested_at TIMESTAMPTZ,
    joined_at TIMESTAMPTZ,
    capture_started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    -- Provider details
    provider TEXT,  -- 'openclaw', 'google_meet_api', 'zoom_api', 'teams_api'
    provider_session_id TEXT,
    join_url TEXT,
    -- Failure info
    failure_reason TEXT,
    failure_code TEXT,
    retry_count INT NOT NULL DEFAULT 0,
    -- Consent tracking
    consent_verified BOOLEAN NOT NULL DEFAULT false,
    consent_method TEXT,  -- 'user_explicit', 'meeting_settings', 'not_required'
    -- Transcript
    transcript_requested BOOLEAN NOT NULL DEFAULT false,
    transcript_delivered BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_mas_user FOREIGN KEY (user_id) REFERENCES public.user_profiles(id) ON DELETE CASCADE,
    CONSTRAINT fk_mas_meeting FOREIGN KEY (meeting_id, user_id) REFERENCES public.meetings(id, user_id) ON DELETE CASCADE,
    CONSTRAINT chk_mas_status CHECK (status IN (
        'scheduled', 'eligible', 'joining', 'waiting_for_admission', 'joined',
        'capturing', 'completed', 'failed', 'cancelled', 'consent_required'
    ))
);

ALTER TABLE public.meeting_attendance_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY mas_tenant_isolation ON public.meeting_attendance_sessions
    FOR ALL
    USING (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
    WITH CHECK (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid);
GRANT ALL ON TABLE public.meeting_attendance_sessions TO agent_app_user, authenticated;

-- Prevent duplicate active sessions for the same meeting
CREATE UNIQUE INDEX IF NOT EXISTS uq_mas_active_meeting
    ON public.meeting_attendance_sessions (user_id, meeting_id)
    WHERE status NOT IN ('completed', 'failed', 'cancelled');

-- -----------------------------------------------------------------------------
-- 3. TRANSCRIPT SOURCES (one per ingest, normalized)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.transcript_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    meeting_id UUID NOT NULL,
    meeting_version INT NOT NULL DEFAULT 1,
    attendance_session_id UUID,  -- NULL if transcript was uploaded manually or from API
    -- Source metadata
    source_type TEXT NOT NULL,  -- 'openclaw_live', 'platform_api', 'manual_upload', 'integration_push'
    source_platform TEXT,       -- 'google_meet', 'zoom', 'teams', 'openclaw'
    -- Content
    document_id UUID,           -- FK to existing documents table
    raw_storage_path TEXT,      -- path in object storage (if raw retained)
    normalized_text TEXT,       -- full normalized transcript text
    -- Status
    completeness TEXT NOT NULL DEFAULT 'unknown',  -- 'partial', 'complete', 'unknown'
    processing_status TEXT NOT NULL DEFAULT 'pending',
    -- 'pending', 'processing', 'completed', 'failed'
    -- Provenance
    source_url TEXT,
    retrieved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    content_hash TEXT,          -- SHA-256 of normalized_text for dedup
    -- Consent & authorization metadata
    consent_verified BOOLEAN NOT NULL DEFAULT false,
    retention_policy TEXT NOT NULL DEFAULT 'standard',  -- 'standard', 'short', 'none'
    -- Participant info (JSON array of {name, id, role})
    participants JSONB NOT NULL DEFAULT '[]',
    -- Timestamps
    meeting_started_at TIMESTAMPTZ,
    meeting_ended_at TIMESTAMPTZ,
    transcript_start_at TIMESTAMPTZ,
    transcript_end_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_ts_user FOREIGN KEY (user_id) REFERENCES public.user_profiles(id) ON DELETE CASCADE,
    CONSTRAINT fk_ts_meeting FOREIGN KEY (meeting_id, user_id) REFERENCES public.meetings(id, user_id) ON DELETE CASCADE,
    CONSTRAINT chk_ts_completeness CHECK (completeness IN ('partial', 'complete', 'unknown')),
    CONSTRAINT chk_ts_processing_status CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed')),
    CONSTRAINT chk_ts_source_type CHECK (source_type IN ('openclaw_live', 'platform_api', 'manual_upload', 'integration_push'))
);

ALTER TABLE public.transcript_sources ENABLE ROW LEVEL SECURITY;
CREATE POLICY ts_tenant_isolation ON public.transcript_sources
    FOR ALL
    USING (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
    WITH CHECK (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid);
GRANT ALL ON TABLE public.transcript_sources TO agent_app_user, authenticated;

-- Duplicate detection index (content_hash per meeting)
CREATE UNIQUE INDEX IF NOT EXISTS uq_ts_content_hash
    ON public.transcript_sources (user_id, meeting_id, content_hash)
    WHERE content_hash IS NOT NULL;

-- -----------------------------------------------------------------------------
-- 4. TRANSCRIPT SEGMENTS (speaker-level segments for intelligence extraction)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.transcript_segments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    transcript_source_id UUID NOT NULL,
    -- Ordering
    sequence_number INT NOT NULL,
    -- Speaker
    speaker_name TEXT,
    speaker_id TEXT,  -- provider-level participant ID if available
    -- Content
    text TEXT NOT NULL,
    -- Timing
    start_offset_ms BIGINT,  -- milliseconds from meeting start
    end_offset_ms BIGINT,
    -- Epistemic classification
    epistemic_class TEXT NOT NULL DEFAULT 'direct_fact',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_seg_user FOREIGN KEY (user_id) REFERENCES public.user_profiles(id) ON DELETE CASCADE,
    CONSTRAINT fk_seg_source FOREIGN KEY (transcript_source_id) REFERENCES public.transcript_sources(id) ON DELETE CASCADE,
    CONSTRAINT chk_seg_epistemic CHECK (epistemic_class IN ('direct_fact', 'user_confirmed', 'model_inference', 'unverified_assumption'))
);

ALTER TABLE public.transcript_segments ENABLE ROW LEVEL SECURITY;
CREATE POLICY seg_tenant_isolation ON public.transcript_segments
    FOR ALL
    USING (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
    WITH CHECK (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid);
GRANT ALL ON TABLE public.transcript_segments TO agent_app_user, authenticated;

-- Fast retrieval by source
CREATE INDEX IF NOT EXISTS idx_ts_seg_source
    ON public.transcript_segments (transcript_source_id, sequence_number);

-- -----------------------------------------------------------------------------
-- 5. INFORMATION GATHERING RUNS (per-meeting research task tracking)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.information_gathering_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    meeting_id UUID NOT NULL,
    background_job_id UUID,
    -- Run type and scope
    run_type TEXT NOT NULL,  -- 'calendar_sync', 'document_sync', 'contact_research',
                             -- 'topic_research', 'project_intelligence', 'hindsight_recall'
    status TEXT NOT NULL DEFAULT 'pending',
    -- 'pending', 'running', 'completed', 'failed', 'skipped'
    -- Inputs
    input_context JSONB NOT NULL DEFAULT '{}',
    -- Outputs
    findings_count INT NOT NULL DEFAULT 0,
    findings_summary TEXT,
    -- Provider used
    provider TEXT,  -- 'openclaw', 'google_calendar', 'hindsight', 'groq', 'web_search'
    -- Cost tracking
    llm_tokens_used INT,
    llm_cost_usd NUMERIC(10, 6),
    -- Error handling
    error_message TEXT,
    retry_count INT NOT NULL DEFAULT 0,
    -- Timing
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Idempotency
    idempotency_key TEXT,
    CONSTRAINT fk_igr_user FOREIGN KEY (user_id) REFERENCES public.user_profiles(id) ON DELETE CASCADE,
    CONSTRAINT fk_igr_meeting FOREIGN KEY (meeting_id, user_id) REFERENCES public.meetings(id, user_id) ON DELETE CASCADE,
    CONSTRAINT chk_igr_run_type CHECK (run_type IN (
        'calendar_sync', 'document_sync', 'contact_research',
        'topic_research', 'project_intelligence', 'hindsight_recall',
        'transcript_analysis', 'briefing_refresh'
    )),
    CONSTRAINT chk_igr_status CHECK (status IN ('pending', 'running', 'completed', 'failed', 'skipped'))
);

ALTER TABLE public.information_gathering_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY igr_tenant_isolation ON public.information_gathering_runs
    FOR ALL
    USING (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
    WITH CHECK (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid);
GRANT ALL ON TABLE public.information_gathering_runs TO agent_app_user, authenticated;

CREATE UNIQUE INDEX IF NOT EXISTS uq_igr_idempotency
    ON public.information_gathering_runs (user_id, meeting_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

-- -----------------------------------------------------------------------------
-- 6. RESEARCH SOURCES (provenance for each gathered fact)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.research_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    gathering_run_id UUID NOT NULL,
    -- What was researched
    subject_type TEXT NOT NULL,  -- 'contact', 'organization', 'topic', 'project', 'meeting'
    subject_id UUID,             -- optional reference to contacts/projects/meetings
    subject_name TEXT,
    -- Source metadata
    source_url TEXT,
    source_title TEXT,
    retrieved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    content_hash TEXT,
    -- Extracted content (under prompt injection containment)
    raw_excerpt TEXT,
    synthesized_claim TEXT,
    epistemic_class TEXT NOT NULL DEFAULT 'unverified_assumption',
    -- Confirmation
    confirmed_at TIMESTAMPTZ,
    confirmed_by TEXT,  -- 'user', 'agent'
    -- Rejection
    rejected_at TIMESTAMPTZ,
    rejection_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_rs_user FOREIGN KEY (user_id) REFERENCES public.user_profiles(id) ON DELETE CASCADE,
    CONSTRAINT fk_rs_run FOREIGN KEY (gathering_run_id) REFERENCES public.information_gathering_runs(id) ON DELETE CASCADE,
    CONSTRAINT chk_rs_epistemic CHECK (epistemic_class IN ('direct_fact', 'user_confirmed', 'model_inference', 'unverified_assumption')),
    CONSTRAINT chk_rs_subject_type CHECK (subject_type IN ('contact', 'organization', 'topic', 'project', 'meeting'))
);

ALTER TABLE public.research_sources ENABLE ROW LEVEL SECURITY;
CREATE POLICY rs_tenant_isolation ON public.research_sources
    FOR ALL
    USING (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
    WITH CHECK (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid);
GRANT ALL ON TABLE public.research_sources TO agent_app_user, authenticated;

-- -----------------------------------------------------------------------------
-- 7. INTEGRATION SYNC STATE (per-integration incremental sync cursors)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.integration_sync_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    integration_type TEXT NOT NULL,  -- 'google_calendar', 'google_docs', 'zoom', 'teams'
    resource_type TEXT NOT NULL,     -- 'events', 'documents', 'meetings'
    sync_token TEXT,                 -- provider-specific cursor/page-token
    sync_anchor TIMESTAMPTZ,         -- time-based anchor when token is unavailable
    last_full_sync_at TIMESTAMPTZ,
    last_incremental_sync_at TIMESTAMPTZ,
    consecutive_errors INT NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_iss_user FOREIGN KEY (user_id) REFERENCES public.user_profiles(id) ON DELETE CASCADE,
    CONSTRAINT uq_iss_user_int_resource UNIQUE (user_id, integration_type, resource_type)
);

ALTER TABLE public.integration_sync_state ENABLE ROW LEVEL SECURITY;
CREATE POLICY iss_tenant_isolation ON public.integration_sync_state
    FOR ALL
    USING (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid)
    WITH CHECK (user_id = NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid);
GRANT ALL ON TABLE public.integration_sync_state TO agent_app_user, authenticated;

-- -----------------------------------------------------------------------------
-- 8. Extend background_jobs job_type check to support new types
-- -----------------------------------------------------------------------------
-- We'll add valid job types by updating the worker; no ALTER CHECK needed since
-- the existing background_jobs table uses TEXT for job_type without enum constraint.

-- -----------------------------------------------------------------------------
-- 9. Add calendar_event_id to meetings for dedup on sync
-- -----------------------------------------------------------------------------
ALTER TABLE public.meetings ADD COLUMN IF NOT EXISTS calendar_event_id TEXT;
ALTER TABLE public.meetings ADD COLUMN IF NOT EXISTS calendar_source TEXT;  -- 'google', 'ical', 'manual'
ALTER TABLE public.meetings ADD COLUMN IF NOT EXISTS sync_last_seen_at TIMESTAMPTZ;

CREATE UNIQUE INDEX IF NOT EXISTS uq_meetings_calendar_event
    ON public.meetings (user_id, calendar_event_id)
    WHERE calendar_event_id IS NOT NULL;

-- Add transcript-related columns to meetings
ALTER TABLE public.meetings ADD COLUMN IF NOT EXISTS has_transcript BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE public.meetings ADD COLUMN IF NOT EXISTS transcript_source_id UUID;
