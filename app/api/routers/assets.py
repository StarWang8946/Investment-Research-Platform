from fastapi import APIRouter, Depends, Query
from psycopg import Connection

from app.db.session import get_conn
from app.services import assets

router = APIRouter(prefix="/assets", tags=["assets"])


@router.post("")
def create_asset(payload: dict, conn: Connection = Depends(get_conn)):
    return assets.create_asset(conn, payload)


@router.get("")
def list_assets(
    asset_type: str | None = None,
    company_code: str | None = None,
    status: str | None = None,
    tag_id: str | None = None,
    tag_code: str | None = None,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    conn: Connection = Depends(get_conn),
):
    return assets.list_assets(conn, page, page_size, asset_type, company_code, status, tag_id=tag_id, tag_code=tag_code, keyword=keyword)


@router.get("/{asset_id}")
def get_asset(asset_id: str, conn: Connection = Depends(get_conn)):
    return assets.get_asset(conn, asset_id)


@router.put("/{asset_id}")
def update_asset(asset_id: str, payload: dict, conn: Connection = Depends(get_conn)):
    return assets.update_asset(conn, asset_id, payload)


@router.get("/{asset_id}/revisions")
def list_revisions(asset_id: str, conn: Connection = Depends(get_conn)):
    return assets.list_revisions(conn, asset_id)


@router.get("/{asset_id}/sources")
def list_sources(asset_id: str, conn: Connection = Depends(get_conn)):
    return assets.list_asset_sources(conn, asset_id)


@router.post("/{asset_id}/export")
def export_asset(asset_id: str, payload: dict | None = None, conn: Connection = Depends(get_conn)):
    payload = payload or {}
    return assets.export_asset(conn, asset_id, payload.get("format", "markdown"))
