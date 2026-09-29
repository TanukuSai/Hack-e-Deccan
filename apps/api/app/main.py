import time
import uuid
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import text

from apps.api.app.core.config import settings
from apps.api.app.core.db import engine
from apps.api.app.providers.hindsight_adapter import HindsightAdapter
from apps.api.app.api.v1 import (
    meetings, contacts, documents, briefings, projects, commitments, preferences, integrations, users, auth
)

logger = logging.getLogger("api.request")

class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        start_time = time.time()
        
        response = await call_next(request)
        
        duration_ms = round((time.time() - start_time) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = str(duration_ms)
        
        logger.info(
            f"[{request_id}] {request.method} {request.url.path} - "
            f"Status: {response.status_code} - {duration_ms}ms"
        )
        return response

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: pool ready
    yield
    # Shutdown
    await engine.dispose()

app = FastAPI(
    title="Meeting Prep Agent API",
    version="1.0.0",
    description="Authoritative API for Meeting Prep Agent",
    lifespan=lifespan,
)

app.add_middleware(CorrelationIdMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register v1 API Routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(projects.router, prefix="/api/v1")
app.include_router(meetings.router, prefix="/api/v1")
app.include_router(contacts.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(briefings.router, prefix="/api/v1")
app.include_router(commitments.router, prefix="/api/v1")
app.include_router(preferences.router, prefix="/api/v1")
app.include_router(integrations.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")

@app.get("/health/live")
async def health_live():
    return {"status": "ok"}

@app.get("/health/ready")
async def health_ready():
    return {"status": "ready"}

@app.get("/health/dependencies")
async def health_dependencies():
    """
    Comprehensive dependency health probe (Gate 6):
    Probes PostgreSQL pool, Groq provider configuration, and Hindsight Memory Cloud.
    """
    dependencies: Dict[str, Any] = {}
    overall_status = "healthy"

    # 1. Database Check
    try:
        t0 = time.time()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1;"))
        db_ms = round((time.time() - t0) * 1000, 2)
        dependencies["database"] = {
            "status": "connected",
            "latency_ms": db_ms,
            "engine": "postgresql"
        }
    except Exception as e:
        dependencies["database"] = {"status": "error", "error": str(e)}
        overall_status = "degraded"

    # 2. LLM Provider (Groq) Check
    dependencies["llm_provider"] = {
        "provider": "groq",
        "model": settings.GROQ_MODEL,
        "status": "configured" if bool(settings.GROQ_API_KEY) else "unconfigured"
    }

    # 3. Contextual Memory (Hindsight) Check
    hindsight = HindsightAdapter()
    if hindsight.enabled:
        h_healthy = await hindsight.is_healthy()
        dependencies["memory_service"] = {
            "provider": "hindsight",
            "endpoint": hindsight.base_url,
            "status": "connected" if h_healthy else "degraded"
        }
        if not h_healthy:
            overall_status = "degraded"
    else:
        dependencies["memory_service"] = {
            "provider": "hindsight",
            "status": "disabled"
        }

    # 4. Storage Check
    dependencies["object_storage"] = {
        "provider": "supabase_storage",
        "bucket": settings.OBJECT_STORAGE_BUCKET,
        "status": "ready"
    }

    return {
        "status": overall_status,
        "timestamp": time.time(),
        "dependencies": dependencies
    }
