from pathlib import Path
import json
import sqlalchemy as sa
from alembic import command
from alembic.config import Config


def run_upgrade(connection, target='head'):
    root=Path(__file__).resolve().parents[1]
    config=Config(str(root/'alembic.ini'))
    config.set_main_option('script_location',str(root/'alembic'))
    config.attributes['connection']=connection
    command.upgrade(config,target)


def test_empty_database_upgrade(tmp_path):
    engine=sa.create_engine(f'sqlite:///{tmp_path / "empty.db"}')
    with engine.begin() as conn:
        run_upgrade(conn)
        tables=set(sa.inspect(conn).get_table_names())
        assert {'users','chat_sessions','chat_messages','roles','menus','role_permissions','user_roles'} <= tables
        cols={c['name'] for c in sa.inspect(conn).get_columns('chat_messages')}
        assert {'parent_id','local_user_id','business_type','duration_ms','cache_status'} <= cols
        run_upgrade(conn)
    engine.dispose()


def test_legacy_backfill_and_unstamped_existing_database(tmp_path):
    engine=sa.create_engine(f'sqlite:///{tmp_path / "legacy.db"}')
    with engine.begin() as conn:
        run_upgrade(conn,'20260908_chat')
        conn.execute(sa.text('CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(100), email VARCHAR(255), department VARCHAR(100), password_hash VARCHAR(255), created_at DATETIME, updated_at DATETIME, employee_id VARCHAR(50), principal_id BIGINT)'))
        conn.execute(sa.text("INSERT INTO users (id, username, email, password_hash) VALUES (1,'alice','a@test','!')"))
        conn.execute(sa.text("INSERT INTO chat_sessions(id,user_id,status) VALUES (1,'alice','active')"))
        conn.execute(sa.text('ALTER TABLE chat_messages ADD COLUMN parent_id INTEGER'))
        conn.execute(sa.text("INSERT INTO chat_messages(id,session_id,role,user_id,category,sequence_no,status,metadata_json) VALUES (1,1,'user','alice','question',1,'completed',:m)"),{'m':json.dumps({'source':'industry_report'})})
        conn.execute(sa.text("INSERT INTO chat_messages(id,session_id,role,user_id,category,sequence_no,status,parent_id,metadata_json) VALUES (2,1,'redis_cache','alice','answer',2,'completed',1,:m)"),{'m':json.dumps({'source':'redis_cache','cache_hit':True})})
        conn.execute(sa.text("INSERT INTO chat_messages(id,session_id,role,user_id,category,sequence_no,status,metadata_json) VALUES (3,1,'user','alice','question',3,'completed',:m)"),{'m':json.dumps({'source':'industry_report'})})
        conn.execute(sa.text("INSERT INTO chat_messages(id,session_id,role,user_id,category,sequence_no,status,metadata_json) VALUES (4,1,'user','alice','question',4,'completed','legacy text')"))
        conn.execute(sa.text('DELETE FROM alembic_version'))
        run_upgrade(conn)
        rows=conn.execute(sa.text('SELECT id,local_user_id,cache_status,execution_status,duration_ms FROM chat_messages ORDER BY id')).mappings().all()
        assert rows[0]['local_user_id']==1 and rows[0]['cache_status']=='hit' and rows[0]['execution_status']=='success'
        assert rows[2]['execution_status']=='unknown' and rows[2]['duration_ms'] is None
        legacy = conn.execute(sa.text('SELECT metadata_json FROM chat_messages WHERE id = 4')).scalar_one()
        assert json.loads(legacy) == {'legacy_raw': 'legacy text'}
        assert next(c for c in sa.inspect(conn).get_columns('chat_messages') if c['name']=='sequence_no')['nullable'] is True
    engine.dispose()
