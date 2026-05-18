from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse

from Api.utils.auth import verify_auth_token


class AuthEnforcer(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path or ""

        # allow unauthenticated access to login/register and assets only
        unauthenticated_allowed = {
            "/",
            "/health",
            "/favicon.ico",
            "/auth/login",
            "/auth/tg/login",
            "/auth/register",
            "/auth/validate",
            "/auth/cookie",
            "/webapp/verify",
        }
        unauthenticated_prefixes = ("/assets", "/static")

        if request.method == "OPTIONS":
            return await call_next(request)

        # if route is public for unauthenticated, allow
        if path in unauthenticated_allowed or any(path.startswith(p) for p in unauthenticated_prefixes):
            return await call_next(request)

        # for all other routes, require valid auth token. app calls all endpoints with token.
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
                token = (request.query_params.get("token") or "").strip()
            if not token:
                token = (request.query_params.get("auth") or "").strip()

        if not token:
            return JSONResponse({"detail": "auth required"}, status_code=401)

        try:
            verify_auth_token(token)
        except Exception:
            return JSONResponse({"detail": "invalid auth token"}, status_code=401)

        # token valid, allow all app routes. endpoint handlers enforce their own auth rules.
        return await call_next(request)
