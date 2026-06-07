from fastapi import APIRouter, Depends
from psycopg import Connection

from app.db.session import get_conn
from app.services import prompts

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.get("")
def list_prompts(agent_name: str | None = None, scenario: str | None = None, status: str | None = None, conn: Connection = Depends(get_conn)):
    return prompts.list_prompts(conn, agent_name, scenario, status)


@router.get("/{template_key}")
def get_prompt(template_key: str, conn: Connection = Depends(get_conn)):
    return prompts.get_prompt_by_key(conn, template_key)


@router.post("")
def create_prompt(payload: dict, conn: Connection = Depends(get_conn)):
    return prompts.create_prompt(conn, payload)


@router.put("/{template_key}")
def update_prompt(template_key: str, payload: dict, conn: Connection = Depends(get_conn)):
    return prompts.update_prompt(conn, template_key, payload)
