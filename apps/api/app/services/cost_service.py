from decimal import Decimal
from typing import Optional, Tuple
from uuid import UUID
import uuid
from sqlalchemy import text
from fastapi import HTTPException, status
from apps.api.app.core.db import get_tenant_session

# Groq Llama 3.3 70B Versatile token rates (USD per token)
PROMPT_TOKEN_RATE = Decimal("0.00000059")      # $0.59 / 1M tokens
COMPLETION_TOKEN_RATE = Decimal("0.00000079")  # $0.79 / 1M tokens
DEFAULT_RESERVATION_COST = Decimal("0.0100")    # $0.01 safe upper reservation per briefing

class BudgetExceededException(HTTPException):
    def __init__(self, detail: str = "Monthly LLM budget limit exceeded. Service suspended."):
        super().__init__(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=detail
        )

class CostService:
    @staticmethod
    async def reserve_budget(
        user_id: str,
        operation_type: str = "briefing",
        model_provider: str = "groq",
        model_name: str = "llama-3.3-70b-versatile",
        job_id: Optional[UUID] = None,
        estimated_cost: Decimal = DEFAULT_RESERVATION_COST
    ) -> UUID:
        """
        Atomically checks user's budget and reserves funds in llm_usage_ledger.
        Raises BudgetExceededException if:
        current_spend + active_reservations + estimated_cost > monthly_budget.
        """
        async with get_tenant_session(user_id) as session:
            # 1. Fetch user profile budget settings with row lock
            res = await session.execute(
                text("""
                SELECT monthly_budget_usd, current_month_spend_usd
                FROM public.user_profiles
                WHERE id = :u_id
                FOR UPDATE;
                """),
                {"u_id": user_id}
            )
            profile = res.mappings().first()
            if not profile:
                raise HTTPException(status_code=404, detail="User profile not found")

            monthly_budget = Decimal(str(profile["monthly_budget_usd"]))
            current_spend = Decimal(str(profile["current_month_spend_usd"]))

            # 2. Sum existing active (unsettled) reservations
            res_sum = await session.execute(
                text("""
                SELECT COALESCE(SUM(reserved_cost_usd), 0) as total_reserved
                FROM public.llm_usage_ledger
                WHERE user_id = :u_id AND status = 'reserved';
                """),
                {"u_id": user_id}
            )
            total_reserved = Decimal(str(res_sum.scalar() or "0"))

            # 3. Check hard ceiling
            if current_spend + total_reserved + estimated_cost > monthly_budget:
                raise BudgetExceededException(
                    f"Monthly budget of ${monthly_budget:.2f} exceeded. Current spend: ${current_spend:.4f}, Active reservations: ${total_reserved:.4f}"
                )

            # 4. Insert ledger reservation row
            ledger_id = uuid.uuid4()
            await session.execute(
                text("""
                INSERT INTO public.llm_usage_ledger (
                    id, user_id, job_id, request_id, operation_type,
                    model_provider, model_name, status, reserved_cost_usd
                )
                VALUES (
                    :id, :user_id, :job_id, :request_id, :operation_type,
                    :model_provider, :model_name, 'reserved', :reserved_cost
                );
                """),
                {
                    "id": str(ledger_id),
                    "user_id": user_id,
                    "job_id": str(job_id) if job_id else None,
                    "request_id": str(uuid.uuid4()),
                    "operation_type": operation_type,
                    "model_provider": model_provider,
                    "model_name": model_name,
                    "reserved_cost": float(estimated_cost)
                }
            )
            return ledger_id

    @staticmethod
    async def settle_reservation(
        user_id: str,
        ledger_id: UUID,
        prompt_tokens: int,
        completion_tokens: int
    ) -> Decimal:
        """
        Settles a reservation with actual token usage, updates the ledger to 'settled',
        and atomically increments user_profiles.current_month_spend_usd.
        """
        actual_cost = (
            Decimal(prompt_tokens) * PROMPT_TOKEN_RATE +
            Decimal(completion_tokens) * COMPLETION_TOKEN_RATE
        ).quantize(Decimal("0.0001"))

        async with get_tenant_session(user_id) as session:
            # Update ledger
            await session.execute(
                text("""
                UPDATE public.llm_usage_ledger
                SET status = 'settled',
                    actual_cost_usd = :actual_cost,
                    prompt_tokens = :prompt_tokens,
                    completion_tokens = :completion_tokens,
                    settled_at = NOW()
                WHERE id = :l_id AND user_id = :u_id;
                """),
                {
                    "l_id": str(ledger_id),
                    "u_id": user_id,
                    "actual_cost": float(actual_cost),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens
                }
            )

            # Increment user profile monthly spend
            await session.execute(
                text("""
                UPDATE public.user_profiles
                SET current_month_spend_usd = current_month_spend_usd + :actual_cost,
                    updated_at = NOW()
                WHERE id = :u_id;
                """),
                {"u_id": user_id, "actual_cost": float(actual_cost)}
            )

        return actual_cost

    @staticmethod
    async def release_reservation(user_id: str, ledger_id: UUID):
        """
        Releases an unsettled reservation on error/timeout/cancellation so that
        the reserved amount is freed and user_profiles spend is NOT incremented.
        """
        async with get_tenant_session(user_id) as session:
            await session.execute(
                text("""
                UPDATE public.llm_usage_ledger
                SET status = 'released',
                    settled_at = NOW()
                WHERE id = :l_id AND user_id = :u_id AND status = 'reserved';
                """),
                {"l_id": str(ledger_id), "u_id": user_id}
            )

    @staticmethod
    async def get_budget_status(user_id: str) -> dict:
        """
        Returns the user's current spend, monthly budget, and threshold warnings:
        - 80%: warning banner
        - 95%: background auto-prep suspended
        - 100%: hard stop
        """
        async with get_tenant_session(user_id) as session:
            res = await session.execute(
                text("SELECT monthly_budget_usd, current_month_spend_usd FROM public.user_profiles WHERE id = :u_id;"),
                {"u_id": user_id}
            )
            profile = res.mappings().first()
            if not profile:
                return {"percentage": 0.0, "status": "normal"}

            budget = float(profile["monthly_budget_usd"])
            spend = float(profile["current_month_spend_usd"])
            pct = (spend / budget * 100.0) if budget > 0 else 100.0

            status_flag = "normal"
            if pct >= 100.0:
                status_flag = "hard_stop"
            elif pct >= 95.0:
                status_flag = "prep_suspended"
            elif pct >= 80.0:
                status_flag = "warning_banner"

            return {
                "monthly_budget_usd": budget,
                "current_month_spend_usd": spend,
                "percentage_used": round(pct, 2),
                "status": status_flag
            }
