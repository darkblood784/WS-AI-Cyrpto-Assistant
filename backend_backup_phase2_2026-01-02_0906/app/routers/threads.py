from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.routers.auth import get_current_user
from app.db import models

router = APIRouter(tags=["threads"])


class ThreadCreateRequest(BaseModel):
    title: str = Field(default="New chat", min_length=1, max_length=200)


@router.post("/threads")
def create_thread(
    payload: ThreadCreateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    t = models.Thread(user_id=current_user.id, title=payload.title)
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"id": t.id, "title": t.title, "created_at": t.created_at.isoformat()}


@router.get("/threads")
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
def get_thread(
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

    msgs = db.execute(
        select(models.Message)
        .where(models.Message.thread_id == t.id)
        .order_by(models.Message.created_at.asc())
    ).scalars().all()

    return {
        "id": t.id,
        "title": t.title,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat(),
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
            for m in msgs
        ],
    }
