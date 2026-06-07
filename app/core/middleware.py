from uuid import uuid4
import json

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or f"req_{uuid4().hex}"
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class ApiResponseMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if not _should_wrap(request, response):
            return response

        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        if not body:
            data = None
        else:
            data = json.loads(body)

        if isinstance(data, dict) and {"code", "message", "data"}.issubset(data.keys()):
            wrapped = data
        else:
            wrapped = {
                "code": 0,
                "message": "ok",
                "data": data,
                "request_id": getattr(request.state, "request_id", None),
            }

        headers = dict(response.headers)
        headers.pop("content-length", None)
        return Response(
            content=json.dumps(wrapped, ensure_ascii=False, default=str),
            status_code=response.status_code,
            media_type="application/json",
            headers=headers,
        )


def _should_wrap(request: Request, response) -> bool:
    if request.url.path in {"/health", "/openapi.json"}:
        return False
    if request.url.path.startswith(("/docs", "/redoc")):
        return False
    content_type = response.headers.get("content-type", "")
    return response.status_code < 400 and content_type.startswith("application/json")
