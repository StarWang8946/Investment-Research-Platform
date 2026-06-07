from fastapi import APIRouter, Depends, Query, Request
from psycopg import Connection

from app.db.session import get_conn
from app.services import tasks

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("")
def create_task(payload: dict, request: Request, conn: Connection = Depends(get_conn)):
    execute = bool(payload.get("execute", True))
    if execute:
        return tasks.create_and_execute_task(conn, payload, getattr(request.state, "request_id", None))
    return tasks.create_task(conn, payload, getattr(request.state, "request_id", None))


@router.get("")
def list_tasks(status: str | None = None, task_type: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), conn: Connection = Depends(get_conn)):
    return tasks.list_tasks(conn, page, page_size, status, task_type)


@router.get("/{task_id}")
def get_task(task_id: str, conn: Connection = Depends(get_conn)):
    return tasks.get_task(conn, task_id)


@router.get("/{task_id}/runs")
def list_task_runs(task_id: str, conn: Connection = Depends(get_conn)):
    return tasks.list_task_runs(conn, task_id)
