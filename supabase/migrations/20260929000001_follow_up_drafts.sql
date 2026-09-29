-- ============================================================================
-- GATE 4: FOLLOW-UP DRAFTS (Draft-Only External Communications)
-- Invariant: Zero client-send endpoints. All communications generated strictly as drafts.
-- ============================================================================

CREATE TABLE IF NOT EXISTS follow_up_drafts (
    id UUID DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    meeting_id UUID NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    recipients JSONB NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'draft' 
        CHECK (status IN ('draft', 'reviewed', 'discarded')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT fk_follow_ups_meeting FOREIGN KEY (meeting_id, user_id) 
        REFERENCES meetings(id, user_id) ON DELETE CASCADE,
    CONSTRAINT uq_follow_ups_id_user UNIQUE (id, user_id)
);

ALTER TABLE follow_up_drafts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_policy ON follow_up_drafts;
CREATE POLICY tenant_isolation_policy ON follow_up_drafts
FOR ALL
USING (user_id::text = current_setting('request.jwt.claim.sub', true))
WITH CHECK (user_id::text = current_setting('request.jwt.claim.sub', true));

GRANT ALL ON TABLE follow_up_drafts TO agent_app_user, authenticated;
