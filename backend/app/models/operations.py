from datetime import datetime
from typing import Optional
from sqlalchemy import Index, func
from sqlmodel import Field, SQLModel

class CallLog(SQLModel, table=True):
    __tablename__ = "call_logs"
    __table_args__ = (Index("ix_call_logs_endpoint_created_at", "endpoint", "created_at"),)
    id: int = Field(default=None, primary_key=True); user_id: int = Field(default=None, index=True)
    endpoint: str = Field(max_length=255, index=True); method: str = Field(max_length=10); status_code: int; duration: float
    ip_address: str = Field(max_length=64); created_at: Optional[datetime] = Field(default=None, index=True, sa_column_kwargs={"server_default": func.now()})

class CallStat(SQLModel, table=True):
    __tablename__ = "call_stats"
    __table_args__ = (Index("ix_call_stats_user_date", "user_id", "date"),)
    id: int = Field(default=None, primary_key=True); user_id: int = Field(default=None, index=True)
    endpoint: str = Field(max_length=255, index=True); date: datetime = Field(index=True); count: int = Field(default=0)
    created_at: Optional[datetime] = Field(default=None, sa_column_kwargs={"server_default": func.now()})

class SensitiveRule(SQLModel, table=True):
    __tablename__ = "sensitive_rules"
    id: int = Field(default=None, primary_key=True); pattern: str; type: str = Field(max_length=50)
    action: str = Field(default="redact", max_length=30); priority: int = Field(default=0); is_active: bool = Field(default=True)
    created_at: Optional[datetime] = Field(default=None, sa_column_kwargs={"server_default": func.now()})

class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"
    id: int = Field(default=None, primary_key=True); user_id: int = Field(default=None); action: str = Field(max_length=100)
    resource: str = Field(max_length=255); details: str = Field(default=""); ip_address: str = Field(default="", max_length=64)
    created_at: Optional[datetime] = Field(default=None, sa_column_kwargs={"server_default": func.now()})
