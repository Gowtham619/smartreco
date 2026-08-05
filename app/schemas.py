from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ProductIn(BaseModel):
    title: str
    description: str
    category: str
    price: float = 0
    level: Optional[str] = None


class ProductOut(BaseModel):
    id: int
    title: str
    description: str
    category: str
    price: float
    level: Optional[str] = None
    sync_status: str

    model_config = ConfigDict(from_attributes=True)


class EventIn(BaseModel):
    event_type: str
    product_id: Optional[int] = None
    query: Optional[str] = None
    meta: Optional[dict[str, Any]] = None
    duration_ms: Optional[int] = None
    ts: Optional[int] = None


class EventBatchIn(BaseModel):
    events: list[EventIn]


class RecommendationItemOut(BaseModel):
    product_id: int
    title: str
    category: str
    price: float
    rank: int
    reason: Optional[str] = None


class RecommendationOut(BaseModel):
    id: int
    narrative: str
    created_at: datetime
    items: list[RecommendationItemOut]
