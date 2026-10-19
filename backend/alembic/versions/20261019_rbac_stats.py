"""Reconcile legacy chat schema, add request accounting and RBAC.

Historical values are backfilled only when their provenance is known.
"""
import json
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import LONGTEXT

revision = '20261019_rbac_stats'
down_revision = '20260908_chat'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    # The old migration only created chat tables. Bootstrap missing user and
    # operational tables as well, without touching any existing rows.
    from sqlmodel import SQLModel
    from app.models import models  # noqa: F401
    SQLModel.metadata.create_all(bind, checkfirst=True)
    additions = {
        'users': [sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
                  sa.Column('local_login_enabled', sa.Boolean(), nullable=False, server_default=sa.true())],
        'chat_sessions': [sa.Column('local_user_id', sa.Integer(), nullable=True),
                          sa.Column('session_type', sa.String(32), nullable=False, server_default='ai_agent'),
                          sa.Column('metadata_json', sa.JSON(), nullable=True),
                          sa.Column('deleted_at', sa.DateTime(), nullable=True)],
        'chat_messages': [sa.Column('local_user_id', sa.Integer(), nullable=True),
                          sa.Column('parent_id', sa.Integer(), nullable=True),
                          sa.Column('updated_at', sa.DateTime(), nullable=True),
                          sa.Column('business_type', sa.String(32), nullable=True),
                          sa.Column('is_stream', sa.Boolean(), nullable=True),
                          sa.Column('cache_status', sa.String(20), nullable=False, server_default='unknown'),
                          sa.Column('execution_status', sa.String(20), nullable=False, server_default='unknown'),
                          sa.Column('completed_at', sa.DateTime(), nullable=True),
                          sa.Column('duration_ms', sa.Float(), nullable=True),
                          sa.Column('error_code', sa.String(64), nullable=True),
                          sa.Column('error_summary', sa.String(255), nullable=True)],
    }
    for table, columns in additions.items():
        existing = {c['name'] for c in sa.inspect(bind).get_columns(table)}
        for column in columns:
            if column.name not in existing:
                op.add_column(table, column)
    message_columns = {c['name']: c for c in sa.inspect(bind).get_columns('chat_messages')}
    if 'sequence_no' in message_columns and not message_columns['sequence_no']['nullable']:
        with op.batch_alter_table('chat_messages') as batch:
            batch.alter_column('sequence_no', existing_type=sa.Integer(), nullable=True)
    _preserve_invalid_metadata(bind)
    if bind.dialect.name == 'mysql':
        with op.batch_alter_table('chat_messages') as batch:
            batch.alter_column('content', existing_type=message_columns['content']['type'], type_=LONGTEXT(), existing_nullable=True)
            batch.alter_column('metadata_json', existing_type=message_columns['metadata_json']['type'], type_=sa.JSON(), existing_nullable=True)
        with op.batch_alter_table('chat_sessions') as batch:
            batch.alter_column('summary', existing_type=sa.String(2000), type_=sa.String(4000), existing_nullable=True)
    indexes = {
        'chat_messages': [('ix_chat_messages_local_user_id', ['local_user_id']),
                          ('ix_chat_messages_business_created', ['business_type', 'created_at']),
                          ('ix_chat_messages_department_created', ['user_department', 'created_at']),
                          ('ix_chat_messages_parent_id', ['parent_id'])],
        'chat_sessions': [('ix_chat_sessions_local_user_id', ['local_user_id'])],
    }
    for table, definitions in indexes.items():
        existing = {i['name'] for i in sa.inspect(bind).get_indexes(table)}
        for name, columns in definitions:
            if name not in existing:
                op.create_index(name, table, columns)
    for table in ('chat_sessions', 'chat_messages'):
        foreign_keys = {tuple(fk['constrained_columns']) for fk in sa.inspect(bind).get_foreign_keys(table)}
        if ('local_user_id',) not in foreign_keys:
            with op.batch_alter_table(table) as batch:
                batch.create_foreign_key(f'fk_{table}_local_user', 'users', ['local_user_id'], ['id'])
    _backfill(bind)


def _preserve_invalid_metadata(bind):
    # Read raw driver values before ORM JSON decoding; retain malformed legacy
    # text in a valid object so old rows remain readable after type conversion.
    for table in ('chat_sessions', 'chat_messages'):
        last = 0
        while True:
            rows = bind.execute(sa.text(f'SELECT id, metadata_json FROM {table} WHERE id > :last ORDER BY id LIMIT 500'), {'last': last}).all()
            if not rows:
                break
            for row_id, value in rows:
                if value is None or not isinstance(value, str):
                    continue
                try:
                    json.loads(value)
                except ValueError:
                    bind.execute(sa.text(f'UPDATE {table} SET metadata_json = :value WHERE id = :id'),
                                 {'id': row_id, 'value': json.dumps({'legacy_raw': value}, ensure_ascii=False)})
            last = rows[-1][0]


def _metadata(value):
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value) if value else {}
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def _backfill(bind):
    metadata = sa.MetaData()
    users = sa.Table('users', metadata, autoload_with=bind)
    sessions = sa.Table('chat_sessions', metadata, autoload_with=bind)
    messages = sa.Table('chat_messages', metadata, autoload_with=bind)
    # Python equality intentionally avoids case-insensitive MySQL collation for identities.
    identities = dict(bind.execute(sa.select(users.c.username, users.c.id)).all())
    for table in (sessions, messages):
        last = 0
        while True:
            rows = bind.execute(sa.select(table.c.id, table.c.user_id).where(table.c.id > last).order_by(table.c.id).limit(500)).all()
            if not rows:
                break
            for row in rows:
                user_id = identities.get(row.user_id)
                if user_id is not None:
                    bind.execute(table.update().where(table.c.id == row.id, table.c.local_user_id.is_(None)).values(local_user_id=user_id))
            last = rows[-1].id
    bind.execute(messages.update().where(messages.c.updated_at.is_(None)).values(updated_at=messages.c.created_at))
    last = 0
    while True:
        questions = bind.execute(sa.select(messages).where(messages.c.id > last, messages.c.role == 'user').order_by(messages.c.id).limit(500)).mappings().all()
        if not questions:
            break
        for question in questions:
            meta = _metadata(question['metadata_json'])
            if meta.get('source') != 'industry_report':
                continue
            values = {'business_type': 'industry_report'}
            answers = bind.execute(sa.select(messages).where(messages.c.parent_id == question['id'], messages.c.category == 'answer').order_by(messages.c.id)).mappings().all()
            if question['cache_status'] in (None, 'unknown'):
                flags = [_metadata(a['metadata_json']).get('cache_hit') for a in answers]
                if True in flags or any(a['role'] == 'redis_cache' for a in answers):
                    values['cache_status'] = 'hit'
                elif False in flags:
                    values['cache_status'] = 'miss'
            for answer in answers:
                data = _metadata(answer['metadata_json'])
                if data.get('source') in {'upstream_sse', 'upstream_sse_nonstream'}:
                    values['is_stream'] = data['source'] == 'upstream_sse'
                confirmed = (data.get('source') == 'upstream_sse' and data.get('completion_event') == 'MESSAGE_COMPLETED' and data.get('finish_reason') == 'STOP') or data.get('source') in {'upstream_sse_nonstream', 'redis_cache'}
                if confirmed and answer['status'] == 'completed' and question['execution_status'] in (None, 'unknown'):
                    values['execution_status'] = 'success'
                    if answer['request_id']:
                        values['request_id'] = answer['request_id']
            bind.execute(messages.update().where(messages.c.id == question['id']).values(**values))
        last = questions[-1]['id']


def downgrade():
    raise RuntimeError('此迁移包含用户授权及历史统计数据；回退请恢复迁移前数据库备份，禁止静默丢弃授权数据')
