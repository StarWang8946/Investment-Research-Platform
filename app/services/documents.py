from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4
import hashlib

from fastapi import UploadFile
from psycopg import Connection

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.services.common import page_bounds, pagination
from app.services.embeddings import embed_text, vector_literal
from app.services.text import estimate_tokens, read_document_text, split_chunks


SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".json", ".html", ".htm", ".pdf", ".docx"}


def _fetch_one(conn: Connection, sql: str, params: tuple = ()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def _fetch_all(conn: Connection, sql: str, params: tuple = ()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def _execute(conn: Connection, sql: str, params: tuple = ()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def _execute_only(conn: Connection, sql: str, params: tuple = ()) -> None:
    with conn.cursor() as cur:
        cur.execute(sql, params)


def upload_document(
    conn: Connection,
    file: UploadFile,
    title: str | None,
    doc_type: str,
    source: str | None,
    company_code: str | None,
    company_name: str | None,
    industry: str | None,
    publish_date: date | None,
    permission_level: str,
) -> dict:
    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    original_name = Path(file.filename or "document").name
    suffix = Path(original_name).suffix.lower()
    stored_name = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid4().hex}{suffix}"
    stored_path = upload_dir / stored_name

    digest = hashlib.sha256()
    with stored_path.open("wb") as out:
        while chunk := file.file.read(1024 * 1024):
            digest.update(chunk)
            out.write(chunk)

    checksum = digest.hexdigest()
    exists = _fetch_one(conn, "SELECT id FROM documents WHERE checksum = %s AND deleted_at IS NULL", (checksum,))
    if exists:
        stored_path.unlink(missing_ok=True)
        raise AppError(2004, "document already exists", 409)

    source_id = f"doc_{datetime.now().strftime('%Y%m%d')}_{uuid4().hex[:8]}"
    row = _execute(
        conn,
        """
        INSERT INTO documents (
            source_id, title, doc_type, source, company_code, company_name, industry,
            publish_date, permission_level, file_name, file_path, file_type, file_size,
            checksum, parse_status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
        RETURNING id, source_id, parse_status
        """,
        (
            source_id,
            title or original_name,
            doc_type,
            source,
            company_code,
            company_name,
            industry,
            publish_date,
            permission_level,
            original_name,
            str(stored_path),
            suffix.lstrip(".") or "bin",
            stored_path.stat().st_size,
            checksum,
        ),
    )
    return dict(row)


def ingest_document(
    conn: Connection,
    document_id: str,
    force_reingest: bool = False,
    parse_strategy_version: str = "v1",
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> dict:
    doc = _fetch_one(conn, "SELECT * FROM documents WHERE id = %s AND deleted_at IS NULL", (document_id,))
    if not doc:
        raise AppError(2001, "document not found", 404)
    if doc["parse_status"] == "parsed" and not force_reingest:
        return {"document_id": document_id, "status": "parsed", "chunk_count": count_chunks(conn, document_id)}

    path = Path(doc["file_path"])
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise AppError(2002, "document type not supported by current parser", 400)

    _execute(conn, "UPDATE documents SET parse_status = 'processing', updated_at = NOW() WHERE id = %s RETURNING id", (document_id,))
    try:
        text = read_document_text(str(path))
        chunks = split_chunks(text, chunk_size, chunk_overlap)
        prepared_chunks = []
        for index, chunk_text in enumerate(chunks):
            prepared_chunks.append(
                {
                    "chunk_id": f"c_{index + 1:04d}",
                    "chunk_index": index,
                    "chunk_text": chunk_text,
                    "char_start": max(index * (chunk_size - chunk_overlap), 0),
                    "char_end": max(index * (chunk_size - chunk_overlap), 0) + len(chunk_text),
                    "token_count": estimate_tokens(chunk_text),
                    "keyword_text": chunk_text[:1000],
                    "embedding_model": get_settings().embedding_model,
                    "embedding": vector_literal(embed_text(chunk_text)),
                }
            )

        with conn.transaction():
            _execute_only(conn, "DELETE FROM document_chunks WHERE document_id = %s", (document_id,))
            for chunk in prepared_chunks:
                _execute(
                    conn,
                    """
                    INSERT INTO document_chunks (
                        document_id, chunk_id, chunk_index, chunk_text, char_start, char_end,
                        token_count, keyword_text, metadata_json, embedding_model, embedding
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '{}'::jsonb, %s, %s::vector)
                    RETURNING id
                    """,
                    (
                        document_id,
                        chunk["chunk_id"],
                        chunk["chunk_index"],
                        chunk["chunk_text"],
                        chunk["char_start"],
                        chunk["char_end"],
                        chunk["token_count"],
                        chunk["keyword_text"],
                        chunk["embedding_model"],
                        chunk["embedding"],
                    ),
                )
            _execute(
                conn,
                """
                UPDATE documents
                SET parse_status = 'parsed', parse_error = NULL, parse_strategy_version = %s, updated_at = NOW()
                WHERE id = %s
                RETURNING id
                """,
                (parse_strategy_version, document_id),
            )
        return {"document_id": document_id, "status": "parsed", "chunk_count": len(chunks)}
    except AppError:
        raise
    except Exception as exc:
        _execute(
            conn,
            "UPDATE documents SET parse_status = 'failed', parse_error = %s, parse_retry_count = parse_retry_count + 1, updated_at = NOW() WHERE id = %s RETURNING id",
            (str(exc), document_id),
        )
        raise AppError(2003, "document parse failed", 500) from exc


def list_documents(conn: Connection, page: int, page_size: int, **filters) -> dict:
    limit, offset = page_bounds(page, page_size)
    where = ["d.deleted_at IS NULL"]
    params: list = []
    for field in ("doc_type", "company_code", "parse_status", "source", "permission_level"):
        if filters.get(field):
            where.append(f"d.{field} = %s")
            params.append(filters[field])
    if filters.get("keyword"):
        where.append("d.title ILIKE %s")
        params.append(f"%{filters['keyword']}%")
    if filters.get("publish_date_start"):
        where.append("d.publish_date >= %s")
        params.append(filters["publish_date_start"])
    if filters.get("publish_date_end"):
        where.append("d.publish_date <= %s")
        params.append(filters["publish_date_end"])

    where_sql = " AND ".join(where)
    total = _fetch_one(conn, f"SELECT COUNT(*) AS count FROM documents d WHERE {where_sql}", tuple(params))["count"]
    rows = _fetch_all(
        conn,
        f"""
        SELECT d.*, COALESCE(array_remove(array_agg(t.tag_name), NULL), ARRAY[]::varchar[]) AS tag_names
        FROM documents d
        LEFT JOIN document_tags dt ON dt.document_id = d.id
        LEFT JOIN tags t ON t.id = dt.tag_id
        WHERE {where_sql}
        GROUP BY d.id
        ORDER BY d.created_at DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [limit, offset]),
    )
    return {"items": [dict(row) for row in rows], "pagination": pagination(page, limit, total)}


def get_document(conn: Connection, document_id: str) -> dict:
    row = _fetch_one(
        conn,
        """
        SELECT d.*, COUNT(dc.id) AS chunk_count
        FROM documents d
        LEFT JOIN document_chunks dc ON dc.document_id = d.id
        WHERE d.id = %s AND d.deleted_at IS NULL
        GROUP BY d.id
        """,
        (document_id,),
    )
    if not row:
        raise AppError(2001, "document not found", 404)
    return dict(row)


def count_chunks(conn: Connection, document_id: str) -> int:
    return _fetch_one(conn, "SELECT COUNT(*) AS count FROM document_chunks WHERE document_id = %s", (document_id,))["count"]


def list_chunks(conn: Connection, document_id: str, page: int, page_size: int) -> dict:
    get_document(conn, document_id)
    limit, offset = page_bounds(page, page_size)
    total = count_chunks(conn, document_id)
    rows = _fetch_all(
        conn,
        """
        SELECT id, chunk_id, chunk_index, chunk_text, content_type, page_no, position_start,
               position_end, section_title, section_path, token_count, summary_text,
               keywords_json, entities_json, is_important
        FROM document_chunks
        WHERE document_id = %s
        ORDER BY chunk_index ASC
        LIMIT %s OFFSET %s
        """,
        (document_id, limit, offset),
    )
    return {"items": [dict(row) for row in rows], "pagination": pagination(page, limit, total)}


def preview_document(conn: Connection, document_id: str, max_chars: int) -> dict:
    doc = get_document(conn, document_id)
    text = read_document_text(doc["file_path"]) if Path(doc["file_path"]).suffix.lower() in SUPPORTED_EXTENSIONS else ""
    return {"document_id": document_id, "text": text[:max_chars], "max_chars": max_chars}


def delete_document(conn: Connection, document_id: str) -> dict:
    row = _execute(conn, "UPDATE documents SET deleted_at = NOW(), updated_at = NOW() WHERE id = %s AND deleted_at IS NULL RETURNING id", (document_id,))
    if not row:
        raise AppError(2001, "document not found", 404)
    return {"document_id": document_id, "deleted": True}
