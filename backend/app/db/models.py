import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Text, Integer, ForeignKey, JSON, Column
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base
from sqlalchemy.dialects.postgresql import UUID, JSONB

def uuid_str() -> str:
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("plans.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="user", nullable=False, index=True)

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
    per_minute_messages_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    context_messages_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    context_chars_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Feature flags (Phase 3)
    chat_basic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    indicators_basic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    indicators_advanced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    strategy_builder: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    exports: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    alerts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    long_term_memory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
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
    pending_followup_type = Column(Text, nullable=True)
    pending_followup_payload = Column(JSONB, nullable=True)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    thread_id: Mapped[str] = mapped_column(String(36), ForeignKey("threads.id"), nullable=False, index=True)

    # "user" | "assistant" | "system"
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

class ThreadSummary(Base):
    __tablename__ = "thread_summaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    thread_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("threads.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    summary_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional field for later automation (we do NOT auto-update it yet)
    covered_until_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    # Optional: actions that target a user (like update/verify)
    target_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)

    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class AbuseEvent(Base):
    __tablename__ = "abuse_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)

    ip: Mapped[str | None] = mapped_column(String, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)

    endpoint: Mapped[str] = mapped_column(String, nullable=False)
    method: Mapped[str] = mapped_column(String, nullable=False)
    mode: Mapped[str | None] = mapped_column(String, nullable=True)

    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    detail: Mapped[str | None] = mapped_column(String, nullable=True)


class ApiCache(Base):
    __tablename__ = "api_cache"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    request_hash: Mapped[str] = mapped_column(String, nullable=False)

    response_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class NewsItem(Base):
    __tablename__ = "news_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    published_at = Column(DateTime, nullable=True)

    # e.g. "BTC", "ETH", or None for general crypto news
    symbol = Column(String(16), nullable=True, index=True)

    source = Column(String(128), nullable=True)
    title = Column(String(512), nullable=False)
    url = Column(String(1024), nullable=False, unique=True, index=True)

    # optional small snippet (not required)
    summary = Column(String(1024), nullable=True)
