from fastapi import APIRouter, Depends
from psycopg import Connection

from app.db.session import get_conn
from app.services import prompts

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.get("")
def list_prompts(agent_name: str | None = None, scenario: str | None = None, status: str | None = None, conn: Connection = Depends(get_conn)):
    return prompts.list_prompts(conn, agent_name, scenario, status)


@router.post("")
def create_prompt(payload: dict, conn: Connection = Depends(get_conn)):
    return prompts.create_prompt(conn, payload)
