import asyncio
from apps.api.app.core.db import engine
from sqlalchemy import text

async def run():
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE public.user_profiles ADD COLUMN IF NOT EXISTS avatar_url TEXT;"))
        print("Successfully added avatar_url to public.user_profiles")

if __name__ == "__main__":
    asyncio.run(run())
