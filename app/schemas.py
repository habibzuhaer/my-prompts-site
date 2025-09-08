from pydantic import BaseModel, EmailStr, validator
from typing import Optional
from datetime import datetime
import uuid

class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: uuid.UUID
    telegram_chat_id: Optional[str] = None
    created_at: datetime
    is_active: bool

    class Config:
        from_attributes = True

class StrategyBase(BaseModel):
    name: str
    source: str
    symbol: str
    condition_type: str
    condition_value: float
    check_interval: int = 300
    notification_type: str = "both"

    @validator('check_interval')
    def check_interval_min_value(cls, v):
        if v < 30:
            raise ValueError('Check interval must be at least 30 seconds')
        return v

class StrategyCreate(StrategyBase):
    pass

class Strategy(StrategyBase):
    id: uuid.UUID
    user_id: uuid.UUID
    is_active: bool
    created_at: datetime
    last_checked: Optional[datetime] = None

    class Config:
        from_attributes = True

class AlertBase(BaseModel):
    message: str
    trigger_value: float

class Alert(AlertBase):
    id: uuid.UUID
    strategy_id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TelegramChatID(BaseModel):
    chat_id: str