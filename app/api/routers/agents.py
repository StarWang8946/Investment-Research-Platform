from fastapi import APIRouter, Depends, Request
from psycopg import Connection

from app.agents.supervisor import route_task
from app.db.session import get_conn

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/route")
def route(payload: dict, request: Request, conn: Connection = Depends(get_conn)):
    return route_task(conn, payload, request_id=getattr(request.state, "request_id", None))
