from psycopg import Connection

from app.core.exceptions import AppError


def list_tags(conn: Connection, tag_type: str | None = None, parent_id: str | None = None, keyword: str | None = None, status: str | None = None) -> dict:
    where = ["1=1"]
    params: list = []
    if tag_type:
        where.append("tag_type = %s")
        params.append(tag_type)
    if parent_id:
        where.append("parent_id = %s")
        params.append(parent_id)
    if keyword:
        where.append("(tag_code ILIKE %s OR tag_name ILIKE %s)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    if status:
        where.append("status = %s")
        params.append(status)
    with conn.cursor() as cur:
        cur.execute(f"SELECT * FROM tags WHERE {' AND '.join(where)} ORDER BY tag_type, tag_name", tuple(params))
        rows = cur.fetchall()
    return {"items": [dict(row) for row in rows]}


def create_tag(conn: Connection, payload: dict) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tags (tag_code, tag_name, tag_type, parent_id, description)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                payload["tag_code"], payload["tag_name"], payload["tag_type"],
                payload.get("parent_id"), payload.get("description"),
            ),
        )
        return dict(cur.fetchone())


def update_tag(conn: Connection, tag_id: str, payload: dict) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tags
            SET tag_name = COALESCE(%s, tag_name),
                description = COALESCE(%s, description),
                status = COALESCE(%s, status),
                updated_at = NOW()
            WHERE id = %s
            RETURNING *
            """,
            (payload.get("tag_name"), payload.get("description"), payload.get("status"), tag_id),
        )
        row = cur.fetchone()
    if not row:
        raise AppError(7001, "tag not found", 404)
    return dict(row)


def attach_tags(conn: Connection, table: str, id_column: str, resource_id: str, tag_ids: list[str]) -> dict:
    with conn.cursor() as cur:
        for tag_id in tag_ids:
            cur.execute(
                f"INSERT INTO {table} ({id_column}, tag_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (resource_id, tag_id),
            )
    return {"id": resource_id, "tag_ids": tag_ids}


def list_resource_tags(conn: Connection, table: str, id_column: str, resource_id: str) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT t.*
            FROM tags t
            JOIN {table} rt ON rt.tag_id = t.id
            WHERE rt.{id_column} = %s
            ORDER BY t.tag_type, t.tag_name
            """,
            (resource_id,),
        )
        rows = cur.fetchall()
    return {"items": [dict(row) for row in rows]}


def detach_tag(conn: Connection, table: str, id_column: str, resource_id: str, tag_id: str) -> dict:
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM {table} WHERE {id_column} = %s AND tag_id = %s", (resource_id, tag_id))
    return {"id": resource_id, "tag_id": tag_id, "deleted": True}
