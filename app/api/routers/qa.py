import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from psycopg import Connection

from app.agents.base_agent import AgentContext
from app.agents.registry import default_agent_registry
from app.agents.supervisor import route_task
from app.db.session import get_conn
from app.services.search import stream_answer_question

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
    template_key: str | None = Field(default=None, max_length=128)
    export_format: str | None = Field(default=None, max_length=16)


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
    result = stream_answer_question(
        conn,
        payload.question,
        top_k=payload.top_k,
        company_code=payload.company_code,
        task_id=payload.task_id,
        asset_id=payload.asset_id,
        request_id=getattr(request.state, "request_id", None),
    )

    def events():
        yield _sse(
            "metadata",
            {
                "question": result["question"],
                "task_id": result["task_id"],
                "answer_provider": result["answer_provider"],
                "embedding_provider": result["embedding_provider"],
            },
        )
        for citation in result["citations"]:
            yield _sse("citation", citation)
        try:
            for chunk in result["answer_stream"]:
                yield _sse("delta", {"text": chunk})
        except Exception as exc:
            yield _sse("error", {"message": str(exc)})
            return
        yield _sse("done", {"task_id": result["task_id"], "citations_count": len(result["citations"])})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
