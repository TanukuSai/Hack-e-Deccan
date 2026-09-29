-- ============================================================================
-- GOOGLE OAUTH & THIRD-PARTY INTEGRATIONS
-- ============================================================================

CREATE TABLE IF NOT EXISTS tenant_integrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    provider TEXT NOT NULL CHECK (provider IN ('google', 'openclaw', 'microsoft', 'slack')),
    status TEXT NOT NULL DEFAULT 'connected' CHECK (status IN ('connected', 'disconnected', 'error')),
    access_token_encrypted TEXT,
    refresh_token_encrypted TEXT,
    token_expires_at TIMESTAMPTZ,
    scopes JSONB NOT NULL DEFAULT '[]',
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_tenant_integrations_user_provider UNIQUE (user_id, provider),
    CONSTRAINT uq_tenant_integrations_id_user UNIQUE (id, user_id)
);

ALTER TABLE tenant_integrations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_policy ON tenant_integrations;
CREATE POLICY tenant_isolation_policy ON tenant_integrations
FOR ALL
USING (user_id::text = current_setting('request.jwt.claim.sub', true))
WITH CHECK (user_id::text = current_setting('request.jwt.claim.sub', true));

GRANT ALL ON TABLE tenant_integrations TO agent_app_user, authenticated;
