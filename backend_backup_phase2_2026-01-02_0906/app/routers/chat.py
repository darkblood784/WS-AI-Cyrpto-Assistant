import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.routers.auth import get_current_user
from app.db import models

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    feature: str = "chat"
    
def utc_bucket_starts_naive() -> tuple[datetime, datetime, datetime]:
    """
    Returns:
      now_aware (UTC aware)
      day_start_naive (UTC start-of-day, naive for DB)
      month_start_naive (UTC start-of-month, naive for DB)
    DB columns are timestamp without time zone, so we store/query naive UTC.
    """
    now = datetime.now(timezone.utc)
    day_start_aware = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    month_start_aware = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    return now, day_start_aware.replace(tzinfo=None), month_start_aware.replace(tzinfo=None)


def get_admin_emails() -> set[str]:
    raw = os.getenv("ADMIN_EMAILS", "").strip()
    if not raw:
        return set()
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def remaining(limit: int | None, used: int) -> int | None:
    if limit is None:
        return None
    r = limit - used
    return r if r > 0 else 0


@router.post("/chat")
def chat_stub(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # 1) Feature gate (Phase 1C requirement: 403 for restricted features)
    if payload.feature != "chat":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Feature not allowed for your plan.",
        )

    # 2) Optional admin bypass (for testing)
    admin_emails = get_admin_emails()
    is_admin_bypass = current_user.email.lower() in admin_emails

    # 3) Load entitlements
    ent = db.execute(
        select(models.PlanEntitlement).where(
            models.PlanEntitlement.plan_id == current_user.plan_id
        )
    ).scalar_one_or_none()

    if not ent:
        raise HTTPException(status_code=500, detail="Missing plan entitlements.")

    daily_limit = None if is_admin_bypass else ent.daily_messages_limit
    monthly_limit = None if is_admin_bypass else ent.monthly_messages_limit

    now_aware, day_start, month_start = utc_bucket_starts_naive()

    # 4) Enforce + increment usage atomically-ish
    # We avoid db.begin() because your Session already starts a transaction.
    try:
        # Day row (lock)
        day_row = db.execute(
            select(models.UsageCounter)
            .where(
                models.UsageCounter.user_id == current_user.id,
                models.UsageCounter.period_type == "day",
                models.UsageCounter.period_start == day_start,
            )
            .with_for_update()
        ).scalar_one_or_none()

        if not day_row:
            day_row = models.UsageCounter(
                user_id=current_user.id,
                period_type="day",
                period_start=day_start,
                messages_used=0,
            )
            db.add(day_row)
            db.flush()

        # Month row (lock)
        month_row = db.execute(
            select(models.UsageCounter)
            .where(
                models.UsageCounter.user_id == current_user.id,
                models.UsageCounter.period_type == "month",
                models.UsageCounter.period_start == month_start,
            )
            .with_for_update()
        ).scalar_one_or_none()

        if not month_row:
            month_row = models.UsageCounter(
                user_id=current_user.id,
                period_type="month",
                period_start=month_start,
                messages_used=0,
            )
            db.add(month_row)
            db.flush()

        daily_used = day_row.messages_used
        monthly_used = month_row.messages_used

        # Check quota BEFORE increment
        if daily_limit is not None and daily_used >= daily_limit:
            raise HTTPException(status_code=429, detail="Daily message quota exceeded.")
        if monthly_limit is not None and monthly_used >= monthly_limit:
            raise HTTPException(status_code=429, detail="Monthly message quota exceeded.")

        # Increment
        day_row.messages_used = daily_used + 1
        month_row.messages_used = monthly_used + 1

        db.commit()

        daily_used_after = day_row.messages_used
        monthly_used_after = month_row.messages_used

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


    # 5) Response (stub only)
    return {
        "ok": True,
        "echo": payload.message,
        "feature": payload.feature,
        "admin_bypass": is_admin_bypass,
        "utc": {
            "now": now_aware.isoformat(),
        },
        "day": {
            "used": daily_used_after,
            "limit": daily_limit,
            "remaining": remaining(daily_limit, daily_used_after),
        },
        "month": {
            "used": monthly_used_after,
            "limit": monthly_limit,
            "remaining": remaining(monthly_limit, monthly_used_after),
        },
    }
