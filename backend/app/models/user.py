from datetime import datetime
from typing import Optional
from sqlalchemy import func
from sqlmodel import BigInteger, Column, Field, SQLModel

class User(SQLModel, table=True):
    __tablename__ = "users"
    id: int = Field(default=None, primary_key=True)
    username: str = Field(max_length=100, unique=True, index=True)
    email: str = Field(max_length=255, unique=True, index=True)
    department: Optional[str] = Field(default=None, max_length=100, index=True)
    password_hash: str = Field(max_length=255)
    created_at: Optional[datetime] = Field(default=None, sa_column_kwargs={"server_default": func.now()})
    updated_at: Optional[datetime] = Field(default=None, sa_column_kwargs={"server_default": func.now(), "onupdate": func.now()})
    employee_id: Optional[str] = Field(default=None, max_length=50, unique=True, index=True)
    principal_id: Optional[int] = Field(
            default=None,
            sa_column=Column(BigInteger, nullable=True),
    )

class TokenBlacklist(SQLModel, table=True):
    __tablename__ = "tokens"
    id: int = Field(default=None, primary_key=True)
    token_hash: str = Field(max_length=64, unique=True, index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    revoked_at: Optional[datetime] = Field(default=None, sa_column_kwargs={"server_default": func.now()})
    expires_at: datetime
