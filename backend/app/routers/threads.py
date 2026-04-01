import os
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, update, delete, func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.routers.auth import get_current_user
from app.db import models

router = APIRouter(tags=["threads"])

# ---------- display-text extraction ----------
_WSAI_SEPARATOR = "--- WSAI Analysis ---"

def _extract_display(full_text: str) -> str:
    """Strip internal contract sections; return only user-facing narrative."""
    if _WSAI_SEPARATOR in full_text:
        return full_text.split(_WSAI_SEPARATOR, 1)[1].strip()
    return full_text
# -----------------------------------------------


class ThreadCreateRequest(BaseModel):
    title: str = Field(default="New chat", min_length=1, max_length=200)


class ThreadUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        v = int(raw)
    except ValueError:
        return default
    if v < 1:
        return 1
    if v > 100000:
        return 100000
    return v


def thread_cap_for_user(db: Session, user: models.User) -> int:
    """
    Plan-based caps by plan code:
      free -> MAX_THREADS_FREE
      plus -> MAX_THREADS_PLUS (fallback MAX_THREADS_BASIC for backward compatibility)
      pro  -> MAX_THREADS_PRO
    Falls back to MAX_THREADS_FREE defaults if something is missing.
    """
    plan = db.execute(select(models.Plan).where(models.Plan.id == user.plan_id)).scalar_one_or_none()
    code = (plan.code if plan else "free").lower()

    if code == "pro":
        return _env_int("MAX_THREADS_PRO", 3000)
    # Support both "plus" (canonical) and legacy "basic" naming.
    if code in ("basic", "plus"):
        plus_cap = _env_int("MAX_THREADS_PLUS", 1500)
        if os.getenv("MAX_THREADS_PLUS", "").strip():
            return plus_cap
        return _env_int("MAX_THREADS_BASIC", plus_cap)
    return _env_int("MAX_THREADS_FREE", 200)


def enforce_thread_cap(db: Session, user: models.User) -> None:
    """If user exceeds plan cap, delete oldest threads (and their messages) until under cap."""
    is_owner = user.role == "owner"
    is_admin = user.role == "admin"
    bypass = is_owner or is_admin
    if bypass:
        return

    cap = thread_cap_for_user(db, user)

    total = db.execute(
        select(func.count(models.Thread.id)).where(models.Thread.user_id == user.id)
    ).scalar_one()

    if total < cap:
        return

    # We need to free at least 1 slot because caller is creating a new thread now.
    to_delete = (total - cap) + 1
    if to_delete < 1:
        to_delete = 1

    victim_ids = db.execute(
        select(models.Thread.id)
        .where(models.Thread.user_id == user.id)
        .order_by(models.Thread.updated_at.asc())
        .limit(to_delete)
    ).scalars().all()

    if not victim_ids:
        return

    db.execute(delete(models.Message).where(models.Message.thread_id.in_(victim_ids)))
    db.execute(delete(models.Thread).where(models.Thread.id.in_(victim_ids)))
    # Caller commits


@router.post("/threads")
@router.post("/chat/threads")
def create_thread(
    payload: ThreadCreateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        enforce_thread_cap(db, current_user)

        t = models.Thread(user_id=current_user.id, title=payload.title)
        db.add(t)
        db.commit()
        db.refresh(t)
        return {"id": t.id, "title": t.title, "created_at": t.created_at.isoformat()}
    except Exception:
        db.rollback()
        raise


@router.get("/threads")
@router.get("/chat/threads")
def list_threads(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    rows = db.execute(
        select(models.Thread)
        .where(models.Thread.user_id == current_user.id)
        .order_by(desc(models.Thread.updated_at))
        .limit(100)
    ).scalars().all()

    return [
        {
            "id": t.id,
            "title": t.title,
            "created_at": t.created_at.isoformat(),
            "updated_at": t.updated_at.isoformat(),
        }
        for t in rows
    ]


@router.get("/threads/{thread_id}")
@router.get("/chat/threads/{thread_id}")
def get_thread(
    thread_id: str,
    limit: int = 50,
    before: str | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if limit < 1:
        limit = 1
    if limit > 200:
        limit = 200

    t = db.execute(
        select(models.Thread).where(
            models.Thread.id == thread_id,
            models.Thread.user_id == current_user.id,
        )
    ).scalar_one_or_none()

    if not t:
        raise HTTPException(status_code=404, detail="Thread not found")

    q = select(models.Message).where(models.Message.thread_id == t.id)

    before_dt = None
    if before:
        try:
            before_dt = datetime.fromisoformat(before)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid before cursor.")
        q = q.where(models.Message.created_at < before_dt)

    q = q.order_by(models.Message.created_at.desc()).limit(limit + 1)

    msgs = db.execute(q).scalars().all()
    has_more = len(msgs) > limit
    msgs = msgs[:limit]

    msgs_sorted = list(reversed(msgs))

    next_before = None
    if has_more and msgs:
        next_before = msgs[-1].created_at.isoformat()

    return {
        "id": t.id,
        "title": t.title,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat(),
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": _extract_display(m.content) if m.role == "assistant" else m.content,
                "created_at": m.created_at.isoformat(),
            }
            for m in msgs_sorted
        ],
        "page": {"limit": limit, "has_more": has_more, "next_before": next_before},
    }


@router.patch("/threads/{thread_id}")
@router.patch("/chat/threads/{thread_id}")
def rename_thread(
    thread_id: str,
    payload: ThreadUpdateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    t = db.execute(
        select(models.Thread).where(
            models.Thread.id == thread_id,
            models.Thread.user_id == current_user.id,
        )
    ).scalar_one_or_none()

    if not t:
        raise HTTPException(status_code=404, detail="Thread not found")

    t.title = payload.title
    t.updated_at = datetime.utcnow()

    try:
        db.commit()
        db.refresh(t)
        return {
            "id": t.id,
            "title": t.title,
            "created_at": t.created_at.isoformat(),
            "updated_at": t.updated_at.isoformat(),
        }
    except Exception:
        db.rollback()
        raise


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/chat/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_thread(
    thread_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    t = db.execute(
        select(models.Thread).where(
            models.Thread.id == thread_id,
            models.Thread.user_id == current_user.id,
        )
    ).scalar_one_or_none()

    if not t:
        raise HTTPException(status_code=404, detail="Thread not found")

    try:
        db.execute(delete(models.Message).where(models.Message.thread_id == thread_id))
        db.execute(delete(models.Thread).where(models.Thread.id == thread_id))
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception:
        db.rollback()
        raise


def touch_thread(db: Session, thread_id: str) -> None:
    db.execute(
        update(models.Thread)
        .where(models.Thread.id == thread_id)
        .values(updated_at=datetime.utcnow())
    )
