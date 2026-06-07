from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from psycopg import Connection

from app.db.session import get_conn
from app.services.search import hybrid_search

router = APIRouter(prefix="/search", tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=10, ge=1, le=50)
    company_code: str | None = Field(default=None, max_length=32)
    doc_type: str | None = Field(default=None, max_length=64)


@router.post("")
def search(payload: SearchRequest, conn: Connection = Depends(get_conn)):
    return hybrid_search(
        conn,
        payload.query,
        top_k=payload.top_k,
        company_code=payload.company_code,
        doc_type=payload.doc_type,
    )


@router.get("")
def search_get(query: str, top_k: int = Query(10, ge=1, le=50), company_code: str | None = None, doc_type: str | None = None, conn: Connection = Depends(get_conn)):
    return hybrid_search(conn, query, top_k, company_code, doc_type)
