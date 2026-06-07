from time import perf_counter

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


def create_and_execute_task(conn: Connection, payload: dict, request_id: str | None = None) -> dict:
    task = create_task(conn, payload, request_id=request_id)
    return execute_task(conn, str(task["id"]), request_id=request_id)


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


def execute_task(conn: Connection, task_id: str, request_id: str | None = None) -> dict:
    from app.agents.supervisor import route_task

    task = get_task(conn, task_id)
    payload = _build_agent_payload(task)
    started = perf_counter()
    start_task(conn, task_id)

    create_task_run(
        conn,
        task_id,
        run_type="agent",
        run_name="orchestrator_agent.route",
        status="running",
        input_payload=payload,
    )
    try:
        result = route_task(conn, payload, request_id=request_id)
        duration_ms = int((perf_counter() - started) * 1000)
        decision = result["decision"]
        update_task_route_agent(conn, task_id, decision["agent"])
        update_task_run_status(
            conn,
            task_id,
            run_type="agent",
            run_name="orchestrator_agent.route",
            status="completed",
            output_payload=decision,
            duration_ms=duration_ms,
        )
        create_task_run(
            conn,
            task_id,
            run_type="agent",
            run_name=decision["agent"],
            status="completed",
            input_payload=payload,
            output_payload={"skill": decision["skill"], "task_type": decision["task_type"]},
            duration_ms=duration_ms,
        )
        updated_task = get_task(conn, task_id)
        return {
            "task": updated_task,
            "decision": decision,
            "result": result.get("result"),
        }
    except Exception as exc:
        duration_ms = int((perf_counter() - started) * 1000)
        fail_task(conn, task_id, str(exc))
        create_task_run(
            conn,
            task_id,
            run_type="agent",
            run_name="orchestrator_agent.route",
            status="failed",
            input_payload=payload,
            duration_ms=duration_ms,
            error_message=str(exc),
        )
        raise


def get_task(conn: Connection, task_id: str) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
        row = cur.fetchone()
    if not row:
        raise AppError(4001, "task not found", 404)
    return dict(row)


def update_task_route_agent(conn: Connection, task_id: str, route_agent: str) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tasks
            SET route_agent = %s, updated_at = NOW()
            WHERE id = %s
            RETURNING *
            """,
            (route_agent, task_id),
        )
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


def update_task_run_status(
    conn: Connection,
    task_id: str,
    run_type: str,
    run_name: str,
    status: str,
    output_payload: dict | None = None,
    duration_ms: int | None = None,
    error_message: str | None = None,
) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE task_runs
            SET status = %s,
                output_payload = COALESCE(%s, output_payload),
                duration_ms = COALESCE(%s, duration_ms),
                error_message = %s
            WHERE id = (
                SELECT id
                FROM task_runs
                WHERE task_id = %s AND run_type = %s AND run_name = %s
                ORDER BY created_at DESC
                LIMIT 1
            )
            RETURNING *
            """,
            (
                status,
                Jsonb(output_payload) if output_payload is not None else None,
                duration_ms,
                error_message[:2000] if error_message else None,
                task_id,
                run_type,
                run_name,
            ),
        )
        row = cur.fetchone()
    if not row:
        raise AppError(4003, "task run not found", 404)
    return dict(row)


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


def _build_agent_payload(task: dict) -> dict:
    input_payload = dict(task.get("input_payload") or {})
    payload = {
        **input_payload,
        "task_type": task["task_type"],
        "task_id": str(task["id"]),
    }
    if task.get("input_text"):
        payload.setdefault("input_text", task["input_text"])
        if task["task_type"] == "qa":
            payload.setdefault("question", task["input_text"])
        elif task["task_type"] in {"memo", "research_memo", "summary", "conclusion", "daily_report", "daily-report", "report"}:
            payload.setdefault("topic", task["input_text"])
    return payload
