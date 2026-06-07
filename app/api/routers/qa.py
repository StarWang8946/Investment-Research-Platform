import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from psycopg import Connection

from app.agents.base_agent import AgentContext
from app.agents.registry import default_agent_registry
from app.agents.supervisor import route_task
from app.db.session import get_conn

router = APIRouter(prefix="/qa", tags=["qa"])


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    company_code: str | None = Field(default=None, max_length=32)
    task_id: str | None = None
    asset_id: str | None = None


class TopicRequest(BaseModel):
    topic: str | None = Field(default=None, max_length=2000)
    question: str | None = Field(default=None, max_length=2000)
    top_k: int = Field(default=8, ge=1, le=20)
    company_code: str | None = Field(default=None, max_length=32)


@router.post("/ask")
def ask(payload: AskRequest, request: Request, conn: Connection = Depends(get_conn)):
    return default_agent_registry.get("research_agent").run(
        conn,
        AgentContext(
            payload=payload.model_dump() | {"task_type": "qa"},
            request_id=getattr(request.state, "request_id", None),
        ),
    )["result"]


@router.post("/ask/stream")
def ask_stream(payload: AskRequest, request: Request, conn: Connection = Depends(get_conn)):
    result = default_agent_registry.get("research_agent").run(
        conn,
        AgentContext(
            payload=payload.model_dump() | {"task_type": "qa"},
            request_id=getattr(request.state, "request_id", None),
        ),
    )["result"]

    def events():
        yield _sse("metadata", {"question": result["question"], "answer_provider": result["answer_provider"], "embedding_provider": result["embedding_provider"]})
        for citation in result["citations"]:
            yield _sse("citation", citation)
        for line in result["answer"].splitlines():
            yield _sse("delta", {"text": line + "\n"})
        yield _sse("done", {"citations_count": len(result["citations"])})

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/memo")
def memo(payload: TopicRequest, conn: Connection = Depends(get_conn)):
    return default_agent_registry.get("research_agent").run(
        conn,
        AgentContext(payload=payload.model_dump() | {"task_type": "memo"}),
    )["result"]


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/daily-report")
def daily_report(payload: TopicRequest, conn: Connection = Depends(get_conn)):
    return route_task(conn, payload.model_dump() | {"task_type": "daily_report"})["result"]
