from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID
import json

from fastapi import HTTPException, status
from sqlalchemy import text

from apps.api.app.core.db import get_tenant_session

class PreferenceService:
    """
    Deterministic Preference Learning Engine (MVP-008).
    Implements mathematical confidence formula: C = clip(B + S - K - D, 0.0, 1.0)
    with reversible undo, multi-scoped preferences, and tenant isolation.
    """

    @staticmethod
    def calculate_confidence(
        source_type: str = "learned",
        positive_signals: int = 0,
        corrections: int = 0,
        days_inactive: int = 0
    ) -> float:
        """
        Calculates confidence score:
        B: Baseline (1.0 for explicit, 0.5 for learned)
        S: Positive reinforcement (0.1 per signal)
        K: Negative friction / overrides (0.15 per correction)
        D: Time decay (0.01 per day inactive, max 0.20)
        """
        baseline = 1.0 if source_type == "explicit" else 0.5
        s = positive_signals * 0.10
        k = corrections * 0.15
        d = min(0.20, days_inactive * 0.01)

        raw_c = baseline + s - k - d
        return max(0.0, min(1.0, round(raw_c, 3)))

    async def list_preferences(
        self,
        user_id: str,
        dimension: Optional[str] = None,
        scope: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Lists active preferences for a tenant with optional dimension/scope filtering.
        """
        async with get_tenant_session(user_id) as session:
            clauses = ["user_id = :u_id"]
            params: Dict[str, Any] = {"u_id": user_id}

            if dimension:
                clauses.append("dimension = :dim")
                params["dim"] = dimension
            if scope:
                clauses.append("scope = :scope")
                params["scope"] = scope

            query = f"""
            SELECT id, user_id, dimension, scope, scope_id, key, value,
                   source_type, confidence, created_at, updated_at
            FROM public.preferences
            WHERE {' AND '.join(clauses)}
            ORDER BY confidence DESC, updated_at DESC;
            """
            res = await session.execute(text(query), params)
            results = []
            for r in res.mappings().all():
                d = dict(r)
                d["confidence"] = float(d["confidence"])
                if isinstance(d.get("value"), str):
                    try:
                        d["value"] = json.loads(d["value"])
                    except Exception:
                        pass
                results.append(d)
            return results

    async def set_explicit_preference(
        self,
        user_id: str,
        dimension: str,
        scope: str,
        scope_id: str,
        key: str,
        value: Any
    ) -> Dict[str, Any]:
        """
        Explicit user preference configuration (confidence = 1.0, source_type = 'explicit').
        """
        async with get_tenant_session(user_id) as session:
            val_str = json.dumps(value)
            clean_scope_id = str(scope_id) if scope_id else ""
            res = await session.execute(
                text("""
                INSERT INTO public.preferences (
                    user_id, dimension, scope, scope_id, key, value,
                    source_type, confidence, created_at, updated_at
                )
                VALUES (
                    :u_id, :dim, :scope, :scope_id, :key, CAST(:val AS JSONB),
                    'explicit', 1.000, NOW(), NOW()
                )
                ON CONFLICT (user_id, dimension, scope, scope_id, key)
                DO UPDATE SET value = CAST(:val AS JSONB), confidence = 1.000, source_type = 'explicit', updated_at = NOW()
                RETURNING id, user_id, dimension, scope, scope_id, key, value,
                          source_type, confidence, created_at, updated_at;
                """),
                {
                    "u_id": user_id,
                    "dim": dimension,
                    "scope": scope,
                    "scope_id": clean_scope_id,
                    "key": key,
                    "val": val_str
                }
            )
            row = res.mappings().first()
            d = dict(row)
            d["confidence"] = float(d["confidence"])
            if isinstance(d.get("value"), str):
                try:
                    d["value"] = json.loads(d["value"])
                except Exception:
                    pass
            return d

    async def learn_preference(
        self,
        user_id: str,
        dimension: str,
        scope: str,
        scope_id: str,
        key: str,
        value: Any,
        positive_signals: int = 1,
        corrections: int = 0
    ) -> Dict[str, Any]:
        """
        Learns an implicit preference from telemetry signals using deterministic confidence formula.
        """
        confidence = self.calculate_confidence(
            source_type="learned",
            positive_signals=positive_signals,
            corrections=corrections
        )

        async with get_tenant_session(user_id) as session:
            val_str = json.dumps(value)
            clean_scope_id = str(scope_id) if scope_id else ""
            res = await session.execute(
                text("""
                INSERT INTO public.preferences (
                    user_id, dimension, scope, scope_id, key, value,
                    source_type, confidence, created_at, updated_at
                )
                VALUES (
                    :u_id, :dim, :scope, :scope_id, :key, CAST(:val AS JSONB),
                    'learned', :conf, NOW(), NOW()
                )
                ON CONFLICT (user_id, dimension, scope, scope_id, key)
                DO UPDATE SET value = CAST(:val AS JSONB), confidence = :conf, source_type = 'learned', updated_at = NOW()
                RETURNING id, user_id, dimension, scope, scope_id, key, value,
                          source_type, confidence, created_at, updated_at;
                """),
                {
                    "u_id": user_id,
                    "dim": dimension,
                    "scope": scope,
                    "scope_id": clean_scope_id,
                    "key": key,
                    "val": val_str,
                    "conf": float(confidence)
                }
            )
            row = res.mappings().first()
            d = dict(row)
            d["confidence"] = float(d["confidence"])
            if isinstance(d.get("value"), str):
                try:
                    d["value"] = json.loads(d["value"])
                except Exception:
                    pass
            return d

    async def undo_learned_preference(
        self,
        user_id: str,
        preference_id: UUID
    ) -> Dict[str, Any]:
        """
        Reversible undo of a learned preference.
        Sets confidence to 0.000 and records audit trace so user maintains absolute control.
        """
        async with get_tenant_session(user_id) as session:
            res = await session.execute(
                text("""
                UPDATE public.preferences
                SET confidence = 0.000,
                    updated_at = NOW()
                WHERE id = :p_id AND user_id = :u_id
                RETURNING id, user_id, dimension, scope, scope_id, key, value,
                          source_type, confidence, created_at, updated_at;
                """),
                {"p_id": str(preference_id), "u_id": user_id}
            )
            row = res.mappings().first()
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Preference {preference_id} not found"
                )
            d = dict(row)
            d["confidence"] = float(d["confidence"])
            if isinstance(d.get("value"), str):
                try:
                    d["value"] = json.loads(d["value"])
                except Exception:
                    pass
            return d
