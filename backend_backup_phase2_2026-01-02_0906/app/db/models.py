import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Text, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base

def uuid_str() -> str:
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("plans.id"), nullable=False)

    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_verification_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_verification_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class PlanEntitlement(Base):
    __tablename__ = "plan_entitlements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("plans.id"), nullable=False, index=True)

    daily_messages_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_messages_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class UsageCounter(Base):
    __tablename__ = "usage_counters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    # 'day' | 'month'
    period_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # UTC bucket start stored as naive timestamp
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    messages_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(200), default="New chat", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    thread_id: Mapped[str] = mapped_column(String(36), ForeignKey("threads.id"), nullable=False, index=True)

    # "user" | "assistant" | "system"
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
