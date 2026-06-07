from psycopg import Connection
from psycopg.types.json import Jsonb

from app.core.exceptions import AppError
from app.services.common import page_bounds, pagination


def create_task(conn: Connection, payload: dict, request_id: str | None = None) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tasks (task_type, task_title, input_text, input_payload, status, priority, route_agent, request_id)
            VALUES (%s, %s, %s, %s, 'pending', %s, %s, %s)
            RETURNING *
            """,
            (
                payload["task_type"], payload.get("task_title"), payload.get("input_text"),
                Jsonb(payload["input_payload"]) if payload.get("input_payload") is not None else None,
                payload.get("priority", "normal"),
                payload.get("route_agent"), request_id,
            ),
        )
        return dict(cur.fetchone())


def create_qa_task(conn: Connection, question: str, top_k: int, company_code: str | None, request_id: str | None = None) -> dict:
    return create_task(
        conn,
        {
            "task_type": "qa",
            "task_title": question[:120],
            "input_text": question,
            "input_payload": {"question": question, "top_k": top_k, "company_code": company_code},
            "route_agent": "qa",
        },
        request_id=request_id,
    )


def get_task(conn: Connection, task_id: str) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
        row = cur.fetchone()
    if not row:
        raise AppError(4001, "task not found", 404)
    return dict(row)


def start_task(conn: Connection, task_id: str) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tasks
            SET status = 'running', started_at = COALESCE(started_at, NOW()), updated_at = NOW(), error_message = NULL
            WHERE id = %s
            RETURNING *
            """,
            (task_id,),
        )
        row = cur.fetchone()
    if not row:
        raise AppError(4001, "task not found", 404)
    return dict(row)


def complete_task(conn: Connection, task_id: str, output_payload: dict, result_summary: str | None = None) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tasks
            SET status = 'completed',
                output_payload = %s,
                result_summary = %s,
                finished_at = NOW(),
                updated_at = NOW(),
                error_message = NULL
            WHERE id = %s
            RETURNING *
            """,
            (Jsonb(output_payload), result_summary, task_id),
        )
        row = cur.fetchone()
    if not row:
        raise AppError(4001, "task not found", 404)
    return dict(row)


def fail_task(conn: Connection, task_id: str, error_message: str) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tasks
            SET status = 'failed',
                error_message = %s,
                finished_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
            RETURNING *
            """,
            (error_message[:2000], task_id),
        )
        row = cur.fetchone()
    if not row:
        raise AppError(4001, "task not found", 404)
    return dict(row)


def create_task_run(
    conn: Connection,
    task_id: str,
    run_type: str,
    run_name: str,
    status: str,
    input_payload: dict | None = None,
    output_payload: dict | None = None,
    duration_ms: int | None = None,
    error_message: str | None = None,
) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO task_runs (
                task_id, run_type, run_name, input_payload, output_payload, status, duration_ms, error_message
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                task_id,
                run_type,
                run_name,
                Jsonb(input_payload) if input_payload is not None else None,
                Jsonb(output_payload) if output_payload is not None else None,
                status,
                duration_ms,
                error_message[:2000] if error_message else None,
            ),
        )
        return dict(cur.fetchone())


def list_tasks(conn: Connection, page: int, page_size: int, status: str | None = None, task_type: str | None = None) -> dict:
    limit, offset = page_bounds(page, page_size)
    where = ["1=1"]
    params: list = []
    if status:
        where.append("status = %s")
        params.append(status)
    if task_type:
        where.append("task_type = %s")
        params.append(task_type)
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS count FROM tasks WHERE {' AND '.join(where)}", tuple(params))
        total = cur.fetchone()["count"]
        cur.execute(
            f"SELECT * FROM tasks WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT %s OFFSET %s",
            tuple(params + [limit, offset]),
        )
        rows = cur.fetchall()
    return {"items": [dict(row) for row in rows], "pagination": pagination(page, limit, total)}


def list_task_runs(conn: Connection, task_id: str) -> dict:
    get_task(conn, task_id)
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM task_runs WHERE task_id = %s ORDER BY created_at DESC", (task_id,))
        rows = cur.fetchall()
    return {"items": [dict(row) for row in rows]}
