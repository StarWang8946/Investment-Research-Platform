from math import ceil
from typing import Any


def page_bounds(page: int, page_size: int) -> tuple[int, int]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    return page_size, (page - 1) * page_size


def pagination(page: int, page_size: int, total: int) -> dict[str, Any]:
    total_pages = ceil(total / page_size) if total else 0
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }


def ok(data: Any = None, message: str = "ok") -> dict[str, Any]:
    return {"code": 0, "message": message, "data": data}


def row_to_dict(row: Any) -> dict[str, Any] | None:
    return dict(row) if row is not None else None
