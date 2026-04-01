from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select, JSON
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.routers.auth import get_current_user
from app.db import models

router = APIRouter(prefix="/admin", tags=["admin"])

Role = Literal["user", "admin", "owner"]


def require_admin_or_owner(current_user: models.User = Depends(get_current_user)) -> models.User:
    if current_user.role not in ("admin", "owner"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only.")
    return current_user

def require_owner(current_user: models.User = Depends(get_current_user)) -> models.User:
    if current_user.role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner only.")
    return current_user

def count_owners(db: Session) -> int:
    return db.execute(
        select(func.count()).select_from(models.User).where(models.User.role == "owner")
    ).scalar_one()

def is_last_owner(db: Session, user_id: str) -> bool:
    u = db.get(models.User, user_id)
    if not u or u.role != "owner":
        return False
    return count_owners(db) <= 1

def snapshot_user(u: models.User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "role": u.role,
        "plan_id": u.plan_id,
        "is_active": u.is_active,
        "is_email_verified": u.is_email_verified,
    }

def write_audit(
    db: Session,
    actor: models.User,
    action: str,
    target_user_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
):
    log = models.AdminAuditLog(
        actor_user_id=actor.id,
        target_user_id=target_user_id,
        action=action,
        before=before,
        after=after,
        ip=ip,
        user_agent=user_agent,
    )
    db.add(log)

def require_admin(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only.")
    return current_user


def count_admins(db: Session) -> int:
    return db.execute(
        select(func.count()).select_from(models.User).where(models.User.role == "admin")
    ).scalar_one()


def is_last_admin(db: Session, user_id: str) -> bool:
    # True if user is admin AND total admins == 1
    u = db.get(models.User, user_id)
    if not u or u.role != "admin":
        return False
    return count_admins(db) <= 1


class UserOut(BaseModel):
    id: str
    email: EmailStr
    role: Role
    plan_id: int
    is_active: bool
    is_email_verified: bool
    created_at: str


class UserUpdateRequest(BaseModel):
    # All optional — only apply what’s provided
    plan_id: int | None = None
    role: Role | None = None
    is_active: bool | None = None


@router.get("/users", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin_or_owner),
    # Pagination
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    # Filtering/search
    email: str | None = Query(default=None, description="Filter by email substring"),
    role: Role | None = Query(default=None),
    is_active: bool | None = Query(default=None),
):
    q = select(models.User).order_by(models.User.created_at.desc())

    if email:
        q = q.where(models.User.email.ilike(f"%{email.strip().lower()}%"))
    if role:
        q = q.where(models.User.role == role)
    if is_active is not None:
        q = q.where(models.User.is_active == is_active)

    rows = db.execute(q.limit(limit).offset(offset)).scalars().all()

    return [
        UserOut(
            id=u.id,
            email=u.email,
            role=u.role,
            plan_id=u.plan_id,
            is_active=u.is_active,
            is_email_verified=u.is_email_verified,
            created_at=u.created_at.isoformat(),
        )
        for u in rows
    ]


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(
    user_id: str,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin_or_owner),
):
    u = db.get(models.User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found.")

    return UserOut(
        id=u.id,
        email=u.email,
        role=u.role,
        plan_id=u.plan_id,
        is_active=u.is_active,
        is_email_verified=u.is_email_verified,
        created_at=u.created_at.isoformat(),
    )


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    payload: UserUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_admin_or_owner),
):
    u = db.get(models.User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found.")

    before = snapshot_user(u)

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    def deny(detail: str, status_code: int = 403):
        # record denied attempt and commit it
        write_audit(
            db=db,
            actor=actor,
            action="user.update_denied",
            target_user_id=u.id,
            before=before,
            after={
                "denied": detail,
                "attempt": payload.model_dump(exclude_none=True),
            },
            ip=ip,
            user_agent=ua,
        )
        db.commit()
        raise HTTPException(status_code=status_code, detail=detail)

    # --- OWNER GUARDS ---
    if u.role == "owner" and actor.role != "owner":
        deny("Only owners can modify owners.")

    if payload.role == "owner" and actor.role != "owner":
        deny("Only owners can grant owner role.")

    if u.role == "owner" and payload.role is not None and payload.role != "owner":
        if is_last_owner(db, u.id):
            deny("You cannot demote the last owner.")

    if u.role == "owner" and payload.is_active is False:
        if is_last_owner(db, u.id):
            deny("You cannot deactivate the last owner.")

    # --- OPTIONAL HARDENING (recommended): only owners can grant/revoke admin ---
    # If you want admins to be able to promote others to admin, delete this block.
    if payload.role in ("admin", "user") and u.role in ("admin", "user"):
        # role change involving admin privileges should be owner-only
        if payload.role != u.role and (u.role == "admin" or payload.role == "admin"):
            if actor.role != "owner":
                deny("Only owners can grant or revoke admin role.")

    # --- ADMIN SAFETY GUARDS ---
    if u.role == "admin" and payload.role == "user" and is_last_admin(db, u.id):
        deny("You cannot demote the last admin.", status_code=400)

    if u.role == "admin" and payload.is_active is False and is_last_admin(db, u.id):
        deny("You cannot deactivate the last admin.", status_code=400)

    # --- Apply changes (after guards) ---
    if payload.plan_id is not None:
        plan_exists = db.execute(
            select(models.Plan.id).where(models.Plan.id == payload.plan_id)
        ).scalar_one_or_none()
        if not plan_exists:
            deny("Invalid plan_id", status_code=400)
        u.plan_id = payload.plan_id

    if payload.role is not None:
        u.role = payload.role

    if payload.is_active is not None:
        u.is_active = payload.is_active

    after = snapshot_user(u)

    # Write SUCCESS audit and commit ONCE (atomic with user update)
    write_audit(
        db=db,
        actor=actor,
        action="user.update",
        target_user_id=u.id,
        before=before,
        after=after,
        ip=ip,
        user_agent=ua,
    )
    db.commit()
    db.refresh(u)

    return UserOut(
        id=u.id,
        email=u.email,
        role=u.role,
        plan_id=u.plan_id,
        is_active=u.is_active,
        is_email_verified=u.is_email_verified,
        created_at=u.created_at.isoformat(),
    )

@router.post("/users/{user_id}/verify-email", response_model=UserOut)
def admin_verify_email(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_admin_or_owner),
):
    u = db.get(models.User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found.")

    before = snapshot_user(u)

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    def deny(detail: str, status_code: int = 403):
        write_audit(
            db=db,
            actor=actor,
            action="user.verify_email_denied",
            target_user_id=u.id,
            before=before,
            after={"denied": detail},
            ip=ip,
            user_agent=ua,
        )
        db.commit()
        raise HTTPException(status_code=status_code, detail=detail)

    # Only owners can modify owners (including verify email)
    if u.role == "owner" and actor.role != "owner":
        deny("Only owners can modify owners.")

    # If already verified, still log it (useful for support visibility)
    if u.is_email_verified:
        after = snapshot_user(u)
        write_audit(
            db=db,
            actor=actor,
            action="user.verify_email_noop",
            target_user_id=u.id,
            before=before,
            after=after,
            ip=ip,
            user_agent=ua,
        )
        db.commit()
        db.refresh(u)
        return UserOut(
            id=u.id,
            email=u.email,
            role=u.role,
            plan_id=u.plan_id,
            is_active=u.is_active,
            is_email_verified=u.is_email_verified,
            created_at=u.created_at.isoformat(),
        )

    # Apply change
    u.is_email_verified = True
    u.email_verification_token = None
    u.email_verification_expires_at = None

    after = snapshot_user(u)

    # Write audit + commit ONCE (atomic enough for this endpoint)
    write_audit(
        db=db,
        actor=actor,
        action="user.verify_email",
        target_user_id=u.id,
        before=before,
        after=after,
        ip=ip,
        user_agent=ua,
    )
    db.commit()
    db.refresh(u)

    return UserOut(
        id=u.id,
        email=u.email,
        role=u.role,
        plan_id=u.plan_id,
        is_active=u.is_active,
        is_email_verified=u.is_email_verified,
        created_at=u.created_at.isoformat(),
    )

@router.get("/audit")
def list_audit_logs(
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin_or_owner),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    action: str | None = None,
    target_user_id: str | None = None,
):
    q = select(models.AdminAuditLog).order_by(models.AdminAuditLog.created_at.desc())

    if action:
        q = q.where(models.AdminAuditLog.action == action)
    if target_user_id:
        q = q.where(models.AdminAuditLog.target_user_id == target_user_id)

    rows = db.execute(q.limit(limit).offset(offset)).scalars().all()

    return [
        {
            "id": r.id,
            "actor_user_id": r.actor_user_id,
            "target_user_id": r.target_user_id,
            "action": r.action,
            "before": r.before,
            "after": r.after,
            "ip": r.ip,
            "user_agent": r.user_agent,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
