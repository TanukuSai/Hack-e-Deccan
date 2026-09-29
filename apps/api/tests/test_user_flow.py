import asyncio
import uuid
from apps.api.app.core.db import engine, get_tenant_session
from sqlalchemy import text

async def test_user_flow():
    test_uid = str(uuid.uuid4())
    test_email = f"oauth_test_{test_uid[:8]}@example.com"
    full_name = "Test OAuth User"
    
    # Test seeding
    async with engine.begin() as conn:
        await conn.execute(
            text("SELECT public.seed_test_user(CAST(:u AS UUID), :e, 25.0, 0.0);"),
            {"u": test_uid, "e": test_email}
        )
        print("Seeded user into auth.users and user_profiles")

    # Test query by email on engine directly
    async with engine.connect() as conn:
        res = await conn.execute(
            text("SELECT id, email, full_name FROM public.user_profiles WHERE email = :e;"),
            {"e": test_email}
        )
        row = res.mappings().first()
        print("Fetched by email on engine:", dict(row) if row else None)

if __name__ == "__main__":
    asyncio.run(test_user_flow())
