import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    user = "user"
    admin = "admin"


class SyncStatus(str, enum.Enum):
    synced = "synced"
    pending = "pending"
    error = "error"


class EventType(str, enum.Enum):
    page_view = "page_view"
    product_view = "product_view"
    search = "search"
    click = "click"
    time_spent = "time_spent"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.user, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    events: Mapped[list["Event"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    recommendations: Mapped[list["Recommendation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    level: Mapped[str] = mapped_column(String(60), nullable=True)
    sync_status: Mapped[SyncStatus] = mapped_column(
        Enum(SyncStatus), default=SyncStatus.pending, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    event_type: Mapped[EventType] = mapped_column(Enum(EventType), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=True)
    query: Mapped[str] = mapped_column(String(255), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    user: Mapped["User"] = relationship(back_populates="events")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_reason: Mapped[str] = mapped_column(String(120), nullable=True)
    model_used: Mapped[str] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    user: Mapped["User"] = relationship(back_populates="recommendations")
    items: Mapped[list["RecommendationItem"]] = relationship(
        back_populates="recommendation", cascade="all, delete-orphan", order_by="RecommendationItem.rank"
    )


class RecommendationItem(Base):
    __tablename__ = "recommendation_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("recommendations.id"), index=True, nullable=False
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=True)

    recommendation: Mapped["Recommendation"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()


class RecommendationState(Base):
    __tablename__ = "recommendation_state"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    last_generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    event_count_at_last_gen: Mapped[int] = mapped_column(Integer, default=0)
    generating: Mapped[bool] = mapped_column(Boolean, default=False)
