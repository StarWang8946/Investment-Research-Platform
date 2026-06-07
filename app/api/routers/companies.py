from typing import Any

from fastapi import APIRouter, Depends, Query
from psycopg import Connection

from app.db.session import get_conn
from app.services import companies

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("")
def list_companies(
    keyword: str | None = None,
    industry_code_l1: str | None = None,
    industry_name_l1: str | None = None,
    market: str | None = None,
    is_active: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    conn: Connection = Depends(get_conn),
):
    return companies.list_companies(conn, page, page_size, keyword, industry_code_l1=industry_code_l1, industry_name_l1=industry_name_l1, market=market, is_active=is_active)


@router.get("/{company_code}")
def get_company(company_code: str, conn: Connection = Depends(get_conn)):
    return companies.get_company(conn, company_code)


@router.post("")
def create_company(payload: dict[str, Any], conn: Connection = Depends(get_conn)):
    return companies.create_company(conn, payload)
