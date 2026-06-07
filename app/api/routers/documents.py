from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, Field, model_validator
from psycopg import Connection

from app.db.session import get_conn
from app.services import documents

router = APIRouter(prefix="/documents", tags=["documents"])


class IngestRequest(BaseModel):
    force_reingest: bool = False
    parse_strategy_version: str = Field(default="v1", min_length=1, max_length=32)
    chunk_size: int = Field(default=800, ge=50, le=3000)
    chunk_overlap: int = Field(default=120, ge=0, le=1000)

    @model_validator(mode="after")
    def validate_overlap(self):
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self


@router.post("")
def upload_document(
    file: Annotated[UploadFile, File()],
    doc_type: Annotated[str, Form()],
    title: Annotated[str | None, Form()] = None,
    source: Annotated[str | None, Form()] = None,
    company_code: Annotated[str | None, Form()] = None,
    company_name: Annotated[str | None, Form()] = None,
    industry: Annotated[str | None, Form()] = None,
    publish_date: Annotated[date | None, Form()] = None,
    permission_level: Annotated[str, Form()] = "internal",
    conn: Connection = Depends(get_conn),
):
    return documents.upload_document(conn, file, title, doc_type, source, company_code, company_name, industry, publish_date, permission_level)


@router.post("/{document_id}/ingest")
def ingest_document(document_id: str, payload: IngestRequest | None = None, conn: Connection = Depends(get_conn)):
    payload = payload or IngestRequest()
    return documents.ingest_document(
        conn,
        document_id,
        force_reingest=payload.force_reingest,
        parse_strategy_version=payload.parse_strategy_version,
        chunk_size=payload.chunk_size,
        chunk_overlap=payload.chunk_overlap,
    )


@router.get("")
def list_documents(
    doc_type: str | None = None,
    company_code: str | None = None,
    keyword: str | None = None,
    parse_status: str | None = None,
    source: str | None = None,
    permission_level: str | None = None,
    publish_date_start: date | None = None,
    publish_date_end: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    conn: Connection = Depends(get_conn),
):
    return documents.list_documents(
        conn,
        page,
        page_size,
        doc_type=doc_type,
        company_code=company_code,
        keyword=keyword,
        parse_status=parse_status,
        source=source,
        permission_level=permission_level,
        publish_date_start=publish_date_start,
        publish_date_end=publish_date_end,
    )


@router.get("/{document_id}")
def get_document(document_id: str, conn: Connection = Depends(get_conn)):
    return documents.get_document(conn, document_id)


@router.get("/{document_id}/chunks")
def list_chunks(document_id: str, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), conn: Connection = Depends(get_conn)):
    return documents.list_chunks(conn, document_id, page, page_size)


@router.get("/{document_id}/preview")
def preview_document(document_id: str, max_chars: int = Query(5000, ge=1, le=50000), conn: Connection = Depends(get_conn)):
    return documents.preview_document(conn, document_id, max_chars)


@router.delete("/{document_id}")
def delete_document(document_id: str, conn: Connection = Depends(get_conn)):
    return documents.delete_document(conn, document_id)
