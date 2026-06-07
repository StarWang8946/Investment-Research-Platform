from pathlib import Path
from psycopg import Connection
from docx import Document

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.services.common import page_bounds, pagination


def create_asset(conn: Connection, payload: dict) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO research_assets (asset_type, title, content_markdown, summary, company_code, industry, task_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                payload["asset_type"], payload["title"], payload["content_markdown"],
                payload.get("summary"), payload.get("company_code"), payload.get("industry"),
                payload.get("task_id"),
            ),
        )
        row = cur.fetchone()
        cur.execute(
            "INSERT INTO asset_revisions (asset_id, version, content_markdown, summary, change_note) VALUES (%s, 1, %s, %s, 'initial')",
            (row["id"], row["content_markdown"], row.get("summary")),
        )
    return dict(row)


def list_assets(conn: Connection, page: int, page_size: int, asset_type: str | None = None, company_code: str | None = None, status: str | None = None) -> dict:
    limit, offset = page_bounds(page, page_size)
    where = ["deleted_at IS NULL"]
    params: list = []
    for field, value in (("asset_type", asset_type), ("company_code", company_code), ("status", status)):
        if value:
            where.append(f"{field} = %s")
            params.append(value)
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS count FROM research_assets WHERE {' AND '.join(where)}", tuple(params))
        total = cur.fetchone()["count"]
        cur.execute(
            f"SELECT * FROM research_assets WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT %s OFFSET %s",
            tuple(params + [limit, offset]),
        )
        rows = cur.fetchall()
    return {"items": [dict(row) for row in rows], "pagination": pagination(page, limit, total)}


def get_asset(conn: Connection, asset_id: str) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM research_assets WHERE id = %s AND deleted_at IS NULL", (asset_id,))
        row = cur.fetchone()
    if not row:
        raise AppError(5001, "asset not found", 404)
    return dict(row)


def update_asset(conn: Connection, asset_id: str, payload: dict) -> dict:
    current = get_asset(conn, asset_id)
    new_version = current["version"] + 1
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE research_assets
            SET title = COALESCE(%s, title),
                content_markdown = COALESCE(%s, content_markdown),
                summary = COALESCE(%s, summary),
                status = COALESCE(%s, status),
                version = %s,
                updated_at = NOW()
            WHERE id = %s
            RETURNING *
            """,
            (
                payload.get("title"), payload.get("content_markdown"), payload.get("summary"),
                payload.get("status"), new_version, asset_id,
            ),
        )
        row = cur.fetchone()
        cur.execute(
            "INSERT INTO asset_revisions (asset_id, version, content_markdown, summary, change_note) VALUES (%s, %s, %s, %s, %s)",
            (asset_id, new_version, row["content_markdown"], row.get("summary"), payload.get("change_note")),
        )
    return dict(row)


def list_revisions(conn: Connection, asset_id: str) -> dict:
    get_asset(conn, asset_id)
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM asset_revisions WHERE asset_id = %s ORDER BY version DESC", (asset_id,))
        rows = cur.fetchall()
    return {"items": [dict(row) for row in rows]}


def export_asset(conn: Connection, asset_id: str, export_format: str = "markdown") -> dict:
    asset = get_asset(conn, asset_id)
    export_dir = Path(get_settings().export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    if export_format in ("markdown", "md"):
        path = export_dir / f"{asset_id}.md"
        path.write_text(asset["content_markdown"], encoding="utf-8")
        return {"asset_id": asset_id, "format": "markdown", "file_path": str(path)}
    if export_format == "docx":
        path = export_dir / f"{asset_id}.docx"
        _write_docx(path, asset["title"], asset["content_markdown"])
        return {"asset_id": asset_id, "format": "docx", "file_path": str(path)}
    raise AppError(5003, "asset export format not supported", 400)


def _write_docx(path: Path, title: str, markdown: str) -> None:
    doc = Document()
    doc.add_heading(title, level=1)
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("# "):
            doc.add_heading(line[2:].strip(), level=1)
        elif line.startswith("## "):
            doc.add_heading(line[3:].strip(), level=2)
        elif line.startswith("### "):
            doc.add_heading(line[4:].strip(), level=3)
        elif line.startswith(("- ", "* ")):
            doc.add_paragraph(line[2:].strip(), style="List Bullet")
        elif line[:3].endswith(". ") and line[0].isdigit():
            doc.add_paragraph(line[3:].strip(), style="List Number")
        else:
            doc.add_paragraph(line)
    doc.save(path)
