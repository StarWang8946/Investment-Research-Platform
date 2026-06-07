from fastapi import APIRouter, Depends
from psycopg import Connection

from app.db.session import get_conn
from app.services import tags

router = APIRouter(tags=["tags"])


@router.get("/tags")
def list_tags(tag_type: str | None = None, parent_id: str | None = None, keyword: str | None = None, status: str | None = None, conn: Connection = Depends(get_conn)):
    return tags.list_tags(conn, tag_type, parent_id, keyword, status)


@router.post("/tags")
def create_tag(payload: dict, conn: Connection = Depends(get_conn)):
    return tags.create_tag(conn, payload)


@router.put("/tags/{tag_id}")
def update_tag(tag_id: str, payload: dict, conn: Connection = Depends(get_conn)):
    return tags.update_tag(conn, tag_id, payload)


@router.post("/documents/{document_id}/tags")
def attach_document_tags(document_id: str, payload: dict, conn: Connection = Depends(get_conn)):
    return tags.attach_tags(conn, "document_tags", "document_id", document_id, payload.get("tag_ids", []))


@router.get("/documents/{document_id}/tags")
def list_document_tags(document_id: str, conn: Connection = Depends(get_conn)):
    return tags.list_resource_tags(conn, "document_tags", "document_id", document_id)


@router.delete("/documents/{document_id}/tags/{tag_id}")
def detach_document_tag(document_id: str, tag_id: str, conn: Connection = Depends(get_conn)):
    return tags.detach_tag(conn, "document_tags", "document_id", document_id, tag_id)


@router.post("/assets/{asset_id}/tags")
def attach_asset_tags(asset_id: str, payload: dict, conn: Connection = Depends(get_conn)):
    return tags.attach_tags(conn, "research_asset_tags", "asset_id", asset_id, payload.get("tag_ids", []))


@router.get("/assets/{asset_id}/tags")
def list_asset_tags(asset_id: str, conn: Connection = Depends(get_conn)):
    return tags.list_resource_tags(conn, "research_asset_tags", "asset_id", asset_id)


@router.delete("/assets/{asset_id}/tags/{tag_id}")
def detach_asset_tag(asset_id: str, tag_id: str, conn: Connection = Depends(get_conn)):
    return tags.detach_tag(conn, "research_asset_tags", "asset_id", asset_id, tag_id)
