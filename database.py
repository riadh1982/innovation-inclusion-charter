"""Durable PostgreSQL in production; SQLite for local development only."""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = os.environ.get('CHARTER_DB_PATH', str(ROOT / 'charter.sqlite3'))


class PostgresSession:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, parameters=()):
        # All application statements are static; parameter values stay bound.
        return self.connection.execute(query.replace('?', '%s'), parameters)


@contextmanager
def conn():
    url = os.environ.get('DATABASE_URL', '')
    if url:
        import psycopg
        from psycopg.rows import dict_row
        with psycopg.connect(url, row_factory=dict_row, connect_timeout=15) as c:
            yield PostgresSession(c)
        return
    if os.environ.get('RENDER'):
        raise RuntimeError('DATABASE_URL is required on Render; temporary SQLite storage is disabled.')
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    try:
        with c:
            yield c
    finally:
        c.close()


def initialize():
    postgres = bool(os.environ.get('DATABASE_URL'))
    primary_key = 'BIGSERIAL PRIMARY KEY' if postgres else 'INTEGER PRIMARY KEY AUTOINCREMENT'
    with conn() as c:
        if not postgres:
            c.execute('PRAGMA journal_mode=WAL')
        c.execute(f"""CREATE TABLE IF NOT EXISTS signatures (
            id {primary_key}, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
            category TEXT NOT NULL, created TEXT NOT NULL, feedback TEXT,
            idea TEXT, feedback_status TEXT NOT NULL DEFAULT 'none',
            publish_name INTEGER NOT NULL DEFAULT 0)""")
        if postgres:
            c.execute('ALTER TABLE signatures ADD COLUMN IF NOT EXISTS publish_name INTEGER NOT NULL DEFAULT 0')
        elif 'publish_name' not in {row['name'] for row in c.execute('PRAGMA table_info(signatures)').fetchall()}:
            c.execute('ALTER TABLE signatures ADD COLUMN publish_name INTEGER NOT NULL DEFAULT 0')
        c.execute('CREATE INDEX IF NOT EXISTS idx_feedback ON signatures(feedback_status, id)')
