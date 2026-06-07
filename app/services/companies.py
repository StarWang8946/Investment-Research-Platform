from psycopg import Connection

from app.core.exceptions import AppError
from app.services.common import page_bounds, pagination


def list_companies(conn: Connection, page: int, page_size: int, keyword: str | None = None, **filters) -> dict:
    limit, offset = page_bounds(page, page_size)
    where = ["1=1"]
    params: list = []
    if keyword:
        where.append("(company_code ILIKE %s OR company_name ILIKE %s OR company_short_name ILIKE %s)")
        params.extend([f"%{keyword}%"] * 3)
    for field in ("industry_code_l1", "industry_name_l1", "market", "is_active"):
        if filters.get(field) is not None:
            where.append(f"{field} = %s")
            params.append(filters[field])
    where_sql = " AND ".join(where)
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS count FROM company_basic_info WHERE {where_sql}", tuple(params))
        total = cur.fetchone()["count"]
        cur.execute(
            f"""
            SELECT id, company_code, company_name, company_short_name, exchange, market,
                   industry_name_l1, is_active
            FROM company_basic_info
            WHERE {where_sql}
            ORDER BY company_code
            LIMIT %s OFFSET %s
            """,
            tuple(params + [limit, offset]),
        )
        rows = cur.fetchall()
    return {"items": [dict(row) for row in rows], "pagination": pagination(page, limit, total)}


def get_company(conn: Connection, company_code: str) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM company_basic_info WHERE company_code = %s", (company_code,))
        row = cur.fetchone()
    if not row:
        raise AppError(6001, "company not found", 404)
    return dict(row)


def create_company(conn: Connection, payload: dict) -> dict:
    fields = [
        "company_code", "company_name", "company_short_name", "exchange", "market",
        "industry_code_l1", "industry_name_l1", "industry_code_l2", "industry_name_l2",
        "security_type", "list_date", "delist_date", "is_active",
    ]
    keys = [key for key in fields if key in payload]
    values = [payload[key] for key in keys]
    placeholders = ", ".join(["%s"] * len(keys))
    with conn.cursor() as cur:
        cur.execute(
            f"INSERT INTO company_basic_info ({', '.join(keys)}) VALUES ({placeholders}) RETURNING *",
            tuple(values),
        )
        return dict(cur.fetchone())
