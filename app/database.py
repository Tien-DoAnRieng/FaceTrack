"""Existing Nest database schema and data are shared without copying records."""
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

import pymysql

ROOT = Path(__file__).resolve().parent.parent


def duplicate(error):
    return (isinstance(error, sqlite3.IntegrityError) and (getattr(error, 'sqlite_errorcode', None) in (1555, 2067) or str(error).startswith(('UNIQUE constraint failed:', 'PRIMARY KEY constraint failed:')))) or (isinstance(error, pymysql.IntegrityError) and error.args[0] == 1062)


class Database:
    def __init__(self):
        self.lock = RLock()
        self.dialect = os.getenv('DB_TYPE', 'mysql' if os.getenv('DB_HOST') else 'sqlite')
        if self.dialect == 'sqlite':
            path = os.getenv('DATABASE_PATH', str(ROOT / 'data/attendance.sqlite'))
            if path != ':memory:' and not Path(path).is_absolute():
                path = str(ROOT / path)
            if path != ':memory:':
                Path(path).resolve().parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
            self.connection.row_factory = sqlite3.Row
            self.connection.executescript((ROOT / 'app/schema.sqlite.sql').read_text(encoding='utf-8'))
            if 'role' not in [r['name'] for r in self.all('PRAGMA table_info(users)')]:
                self.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'student' CHECK(role IN ('admin','teacher','student','ai_service'))")
        elif self.dialect == 'mysql':
            name = os.getenv('DB_DATABASE', 'faceid_attendance')
            if not re.fullmatch(r'[A-Za-z0-9_]{1,64}', name):
                raise ValueError('Invalid DB_DATABASE')
            self.connection = pymysql.connect(host=os.getenv('DB_HOST', 'localhost'), port=int(os.getenv('DB_PORT', '3306')), user=os.getenv('DB_USERNAME', 'root'), password=os.getenv('DB_PASSWORD', ''), charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor, autocommit=True, connect_timeout=10)
            self.execute(f'CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_ci')
            self.connection.select_db(name)
            for sql in (ROOT / 'app/schema.mysql.sql').read_text(encoding='utf-8').split(';'):
                if sql.strip():
                    self.execute(sql)
            if not self.all("SHOW COLUMNS FROM users LIKE 'role'"):
                self.execute("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'student'")
        else:
            raise ValueError('DB_TYPE must be mysql or sqlite')

    def all(self, sql, values=()):
        with self.lock:
            if self.dialect == 'sqlite':
                return [dict(row) for row in self.connection.execute(sql, values).fetchall()]
            with self.connection.cursor() as cursor:
                cursor.execute(sql.replace('?', '%s'), values)
                return list(cursor.fetchall())

    def execute(self, sql, values=()):
        with self.lock:
            if self.dialect == 'sqlite':
                return self.connection.execute(sql, values).lastrowid
            with self.connection.cursor() as cursor:
                cursor.execute(sql.replace('?', '%s'), values)
                return cursor.lastrowid

    @contextmanager
    def transaction(self):
        with self.lock:
            if self.dialect == 'sqlite':
                self.connection.execute('BEGIN IMMEDIATE')
            else:
                self.connection.begin()
            try:
                yield self
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise

    def close(self):
        self.connection.close()
