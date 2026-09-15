"""add chat sessions and messages"""
from alembic import op
import sqlalchemy as sa

revision = "20260908_chat"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("user_department", sa.String(255)),
        sa.Column("biz_key", sa.String(255)), sa.Column("title", sa.String(255)),
        sa.Column("summary", sa.String(2000)), sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_chat_sessions_user_created", "chat_sessions", ["user_id", "created_at"])
    op.create_index("ix_chat_sessions_user_biz_key", "chat_sessions", ["user_id", "biz_key"])
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False), sa.Column("content", sa.Text()),
        sa.Column("message_type", sa.String(32), nullable=False, server_default="text"),
        sa.Column("user_id", sa.String(255)), sa.Column("user_department", sa.String(255)),
        sa.Column("category", sa.String(32), nullable=False, server_default="question"),
        sa.Column("sequence_no", sa.Integer(), nullable=False), sa.Column("request_id", sa.String(255)),
        sa.Column("status", sa.String(30), nullable=False, server_default="completed"), sa.Column("metadata_json", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_chat_messages_session_sequence", "chat_messages", ["session_id", "sequence_no"])
    op.create_index("ix_chat_messages_session_created", "chat_messages", ["session_id", "created_at"])

def downgrade() -> None:
    op.drop_index("ix_chat_messages_session_created", table_name="chat_messages")
    op.drop_index("ix_chat_messages_session_sequence", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_chat_sessions_user_biz_key", table_name="chat_sessions")
    op.drop_index("ix_chat_sessions_user_created", table_name="chat_sessions")
    op.drop_table("chat_sessions")
