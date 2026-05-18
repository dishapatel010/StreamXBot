from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse

from Api.utils.auth import verify_auth_token


class AuthEnforcer(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path or ""

        # allow simple public assets, health, and auth endpoints needed for login/registration
        allowed_exact = {
            "/",
            "/health",
            "/favicon.ico",
            "/auth/login",
            "/auth/tg/login",
            "/auth/register",
            "/auth/validate",
            "/auth/cookie",
        }
        allowed_prefixes = ("/assets", "/static")

        if request.method == "OPTIONS":
            return await call_next(request)

        if path in allowed_exact or any(path.startswith(p) for p in allowed_prefixes):
            return await call_next(request)

        # require auth token for every other API route
        token = ""
        auth_header = (request.headers.get("authorization") or request.headers.get("Authorization") or "").strip()
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
        elif (request.headers.get("x-auth-token") or request.headers.get("X-Auth-Token") or "").strip():
            token = (request.headers.get("x-auth-token") or request.headers.get("X-Auth-Token") or "").strip()
        else:
            token = (request.cookies.get("auth_token") or "").strip()
            if not token:
                token = (request.cookies.get("token") or "").strip()

        if not token:
            return JSONResponse({"detail": "auth required"}, status_code=401)

        try:
            verify_auth_token(token)
        except Exception:
            return JSONResponse({"detail": "invalid auth token"}, status_code=401)

        return await call_next(request)
