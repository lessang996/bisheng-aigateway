from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Index, Text, func
from sqlmodel import JSON, DateTime, Field, Relationship, SQLModel
from sqlalchemy.dialects.mysql import LONGTEXT

class ChatSession(SQLModel, table=True):
    __tablename__ = "chat_sessions"
    __table_args__ = (Index("ix_chat_sessions_user_created", "user_id", "created_at"), Index("ix_chat_sessions_user_biz_key", "user_id", "biz_key"))
    id: int = Field(default=None, primary_key=True)
    user_id: str = Field(max_length=255, index=True)
    user_department: Optional[str] = Field(default=None, index=True)
    biz_key: Optional[str] = Field(
        default=None,
        max_length=255,
        description="业务侧会话唯一标识",
    )
    title: Optional[str] = Field(default=None,max_length=255,description="会话标题",)
    summary: Optional[str] = Field(default=None, max_length=4000)
    status: str = Field(default="active", max_length=30, index=True)
    session_type: str = Field(
        default="ai_agent",
        max_length=32,
        index=True,
        description="会话类型",
    )
    metadata_json: Optional[dict] = Field(
        default=None,
        sa_column=Column(
            JSON,
            nullable=True,
        ),
        description="扩展元数据",
    )
    created_at: Optional[datetime] = Field(default=None, sa_column_kwargs={"server_default": func.now()})
    updated_at: Optional[datetime] = Field(default=None, sa_column_kwargs={"server_default": func.now(), "onupdate": func.now()})
    deleted_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(
            DateTime(3),
            nullable=True,
        ),
    )
    messages: list["ChatMessage"] = Relationship(back_populates="session", sa_relationship_kwargs={"cascade": "all, delete-orphan"})

class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_messages_session_sequence", "session_id"), Index("ix_chat_messages_session_created", "session_id", "created_at"))
    id: int = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="chat_sessions.id", index=True)
    role: str = Field(max_length=20, index=True,description="角色，user/assistant/system")

    content: Optional[str] = Field(default=None, sa_type=LONGTEXT)
    message_type: str = Field(default="text", max_length=32)
    user_id: Optional[str] = Field(default=None, index=True)
    user_department: Optional[str] = Field(default=None, index=True)
    parent_id: Optional[int] = Field(
        default=None,
        foreign_key="chat_messages.id",
        description="父消息ID，用于引用、重新生成、分支对话",
    )
       
    category: str = Field(
        default="question",
        max_length=32,
        nullable=False,
        description="消息类别，question/answer/feedback",
    )
    request_id: Optional[str] = Field(default=None, max_length=255, index=True)
    status: str = Field(default="completed", max_length=30)
    metadata_json: Optional[dict] = Field(
        default=None,
        sa_column=Column(
            JSON,
            nullable=True,
        ),
    )
    
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(
            DateTime(3),
            nullable=False,
            server_default=func.now(),
        ),
    )

    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(
            DateTime(3),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )
    session: Optional[ChatSession] = Relationship(back_populates="messages")
