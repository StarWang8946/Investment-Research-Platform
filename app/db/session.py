from collections.abc import Generator

import psycopg
from psycopg.rows import dict_row

from app.core.config import get_settings


def get_conn() -> Generator[psycopg.Connection, None, None]:
    conn = psycopg.connect(get_settings().database_url, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
