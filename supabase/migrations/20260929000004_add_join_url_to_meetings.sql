-- =============================================================================
-- Migration: Add join_url to meetings for live attendance and OpenClaw bot
-- =============================================================================
ALTER TABLE public.meetings ADD COLUMN IF NOT EXISTS join_url TEXT;
GRANT ALL ON TABLE public.meetings TO agent_app_user, authenticated, postgres;
