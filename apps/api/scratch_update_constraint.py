import asyncio
from apps.api.app.core.db import engine
from sqlalchemy import text

async def update_constraints():
    async with engine.begin() as conn:
        res = await conn.execute(text("""
            SELECT conname, pg_get_constraintdef(c.oid)
            FROM pg_constraint c
            JOIN pg_namespace n ON n.oid = c.connamespace
            WHERE c.conrelid = 'public.background_jobs'::regclass;
        """))
        for r in res.fetchall():
            print("Existing constraint:", r)
        
        await conn.execute(text("ALTER TABLE public.background_jobs DROP CONSTRAINT IF EXISTS background_jobs_job_type_check;"))
        await conn.execute(text("""
            ALTER TABLE public.background_jobs ADD CONSTRAINT background_jobs_job_type_check 
            CHECK (job_type IN ('prep_meeting', 'refresh_briefing', 'parse_document', 'extract_outcomes', 'memory_sync', 'calendar_sync', 'transcript_analysis', 'openclaw_recon', 'attendance_join'));
        """))
        print("Updated background_jobs constraint successfully")

if __name__ == "__main__":
    asyncio.run(update_constraints())
