from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_ENV: str = "development"
    APP_BASE_URL: str = "http://localhost:3000"
    API_BASE_URL: str = "http://localhost:8000"

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/postgres"

    # Supabase Auth
    SUPABASE_URL: str = "http://localhost:54321"
    SUPABASE_ANON_KEY: str = "anon-key"
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None
    SUPABASE_JWT_SECRET: str = "secret"
    SUPABASE_PROJECT_REF: str = ""

    # Supabase Storage / Object Storage
    OBJECT_STORAGE_ENDPOINT: str = "http://localhost:54321/storage/v1"
    OBJECT_STORAGE_BUCKET: str = "meeting-documents"
    OBJECT_STORAGE_ACCESS_KEY: Optional[str] = None
    OBJECT_STORAGE_SECRET_KEY: Optional[str] = None

    # LLM Provider
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Fallback LLM Provider
    FALLBACK_LLM_PROVIDER: Optional[str] = None
    FALLBACK_LLM_API_KEY: Optional[str] = None
    FALLBACK_LLM_MODEL: Optional[str] = None

    # Hindsight Memory Service
    HINDSIGHT_ENABLED: bool = False
    HINDSIGHT_BASE_URL: str = "https://api.hindsight.vectorize.io"
    HINDSIGHT_API_KEY: Optional[str] = None
    HINDSIGHT_TIMEOUT_SECONDS: int = 10
    HINDSIGHT_MAX_RECALL_ITEMS: int = 8

    # Cost Enforcement
    MONTHLY_LLM_BUDGET: float = 25.00

settings = Settings()
