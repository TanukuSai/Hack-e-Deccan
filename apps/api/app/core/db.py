from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from apps.api.app.core.config import settings

from sqlalchemy.pool import NullPool

DATABASE_URL = settings.DATABASE_URL

engine = create_async_engine(
    DATABASE_URL,
    poolclass=NullPool,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

@asynccontextmanager
async def get_tenant_session(user_id: str) -> AsyncGenerator[AsyncSession, None]:
    """
    Provides a tenant-scoped database session with Supabase RLS enforced.
    
    1. Checks out connection.
    2. Begins transaction.
    3. Sets role to authenticated and injects the JWT user_id claim.
    4. Yields session.
    5. On exit, rolls back or commits, ensuring isolation.
    """
    async with AsyncSessionLocal() as session:
        try:
            async with session.begin():
                # Set the role and JWT claim for RLS
                await session.execute(text("SET LOCAL ROLE authenticated;"))
                await session.execute(
                    text("SELECT set_config('request.jwt.claim.sub', :user_id, true);"),
                    {"user_id": str(user_id)}
                )
                yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            # Defense in depth: clear session state
            try:
                await session.execute(text("RESET ALL;"))
            except Exception:
                pass
