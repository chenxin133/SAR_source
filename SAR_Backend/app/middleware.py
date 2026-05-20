from __future__ import annotations

import json
import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import get_settings
from app.redis_client import get_redis


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        response: Response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if settings.rate_limit_requests <= 0:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        window = settings.rate_limit_window_seconds
        limit = settings.rate_limit_requests

        now = int(time.time())
        key = f"rl:{client_ip}:{request.url.path}:{now // window}"

        r = get_redis()
        try:
            pipe = r.pipeline()
            pipe.incr(key, 1)
            pipe.expire(key, window + 1)
            count, _ = pipe.execute()
        except Exception:
            return await call_next(request)

        if int(count) > limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too Many Requests"},
                headers={"retry-after": str(window)},
            )
        return await call_next(request)


class JsonLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = int((time.perf_counter() - start) * 1000)
            request_id = getattr(request.state, "request_id", None)
            entry = {
                "ts": int(time.time()),
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": getattr(response, "status_code", 500),
                "duration_ms": duration_ms,
            }
            print(json.dumps(entry, ensure_ascii=False))

