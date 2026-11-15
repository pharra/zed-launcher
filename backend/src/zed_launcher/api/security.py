from __future__ import annotations

import secrets

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class TokenMiddleware(BaseHTTPMiddleware):
    """Protect the local API with a per-session token."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/api") and path != "/api/v1/health":
            expected = getattr(request.app.state, "token", "")
            provided = request.headers.get("x-zed-token") or request.query_params.get("token") or ""
            if not expected or not secrets.compare_digest(str(provided), str(expected)):
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
        return await call_next(request)
