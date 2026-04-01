from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.routers.auth import get_current_user
from app.db import models

router = APIRouter(tags=["plans"])


@router.get("/plans")
def get_plans(db: Session = Depends(get_db)):
    plans = db.execute(select(models.Plan).order_by(models.Plan.code.asc())).scalars().all()
    return [{"id": p.id, "code": p.code, "name": p.name} for p in plans]


@router.get("/entitlements")
def get_entitlements(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ent = db.execute(
        select(models.PlanEntitlement).where(models.PlanEntitlement.plan_id == current_user.plan_id)
    ).scalars().first()

    if not ent:
        return {"plan_id": current_user.plan_id, "daily_messages_limit": None, "monthly_messages_limit": None}

    return {
        "plan_id": current_user.plan_id,
        "daily_messages_limit": ent.daily_messages_limit,
        "monthly_messages_limit": ent.monthly_messages_limit,
    }


@router.get("/usage")
def get_usage(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 1) Load entitlements for current user's plan (limits come from DB)
    ent = db.execute(
        select(models.PlanEntitlement).where(
            models.PlanEntitlement.plan_id == current_user.plan_id
        )
    ).scalars().first()

    daily_limit = ent.daily_messages_limit if ent else None
    monthly_limit = ent.monthly_messages_limit if ent else None

    # 2) Compute UTC bucket starts (aware) + store/query as naive (DB is timestamp without tz)
    now = datetime.now(timezone.utc)
    day_start_aware = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    month_start_aware = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    day_start = day_start_aware.replace(tzinfo=None)
    month_start = month_start_aware.replace(tzinfo=None)

    # 3) Read usage counters (missing row => used 0). NO WRITES ON GET.
    daily_row = db.execute(
        select(models.UsageCounter).where(
            models.UsageCounter.user_id == current_user.id,
            models.UsageCounter.period_type == "day",
            models.UsageCounter.period_start == day_start,
        )
    ).scalars().first()

    monthly_row = db.execute(
        select(models.UsageCounter).where(
            models.UsageCounter.user_id == current_user.id,
            models.UsageCounter.period_type == "month",
            models.UsageCounter.period_start == month_start,
        )
    ).scalars().first()

    daily_used = daily_row.messages_used if daily_row else 0
    monthly_used = monthly_row.messages_used if monthly_row else 0

    def calc_remaining(limit: int | None, used: int) -> int | None:
        if limit is None:
            return None
        r = limit - used
        return r if r > 0 else 0

    return {
        "plan_id": current_user.plan_id,
        "utc": {
            "now": now.isoformat(),
            "day_start": day_start_aware.isoformat(),
            "month_start": month_start_aware.isoformat(),
        },
        "day": {
            "used": daily_used,
            "limit": daily_limit,
            "remaining": calc_remaining(daily_limit, daily_used),
        },
        "month": {
            "used": monthly_used,
            "limit": monthly_limit,
            "remaining": calc_remaining(monthly_limit, monthly_used),
        },
    }
