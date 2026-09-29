import asyncio
from apps.api.app.core.db import engine
from sqlalchemy import text

async def main():
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT prosrc FROM pg_proc WHERE proname = 'seed_test_user'"))
        row = res.scalar()
        print("SEED_TEST_USER DEFINITION:")
        print(row)
        
        res = await conn.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'user_profiles'"))
        print("\nUSER_PROFILES COLUMNS:")
        for r in res.fetchall():
            print(f"  {r[0]}: {r[1]}")

        res = await conn.execute(text("SELECT column_name, is_nullable, column_default FROM information_schema.columns WHERE table_schema = 'auth' AND table_name = 'users' AND is_nullable = 'NO'"))
        print("\nNOT NULL COLUMNS IN auth.users:")
        for r in res.fetchall():
            print(f"  {r[0]}: default={r[2]}")

        res = await conn.execute(text("SELECT column_name, is_nullable, column_default FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'user_profiles' AND is_nullable = 'NO'"))
        print("\nNOT NULL COLUMNS IN public.user_profiles:")
        for r in res.fetchall():
            print(f"  {r[0]}: default={r[2]}")

if __name__ == "__main__":
    asyncio.run(main())
