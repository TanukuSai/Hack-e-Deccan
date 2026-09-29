import jwt
from typing import Optional
from fastapi import Header, HTTPException, status, Depends
from apps.api.app.core.config import settings

def get_current_user_id(
    authorization: Optional[str] = Header(None),
    x_dev_user_id: Optional[str] = Header(None)
) -> str:
    """
    Extracts and verifies the tenant/user UUID from the Supabase JWT Bearer token.
    In development mode, falls back to X-Dev-User-Id if provided for testing.
    """
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        try:
            # Supabase tokens are signed with SUPABASE_JWT_SECRET using HS256
            payload = jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                options={"verify_aud": False}
            )
            sub = payload.get("sub")
            if not sub:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token claims: missing sub"
                )
            return sub
        except jwt.PyJWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"JWT validation failed: {str(e)}"
            )

    # In development mode, allow dev user header for testing
    if settings.APP_ENV == "development" and x_dev_user_id:
        return x_dev_user_id

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid Authorization header"
    )

def create_access_token(payload: dict) -> str:
    """
    Helper to generate a signed Supabase JWT token for testing and tenant authentication.
    """
    return jwt.encode(payload, settings.SUPABASE_JWT_SECRET, algorithm="HS256")
