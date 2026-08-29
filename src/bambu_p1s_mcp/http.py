from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp

from bambu_p1s_mcp.config import Settings
from bambu_p1s_mcp.server import mcp


class BearerTokenMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, token: str) -> None:
        super().__init__(app)
        self.token = token

    async def dispatch(self, request: Request, call_next):
        if request.url.path in {"/health", "/"}:
            return await call_next(request)
        header = request.headers.get("authorization", "")
        expected = f"Bearer {self.token}"
        if header != expected:
            return Response("unauthorized", status_code=401)
        return await call_next(request)


async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "name": "bambu-p1s-mcp"})


def build_http_app(settings: Settings):
    # FastMCP already mounts Streamable HTTP at /mcp.
    app = mcp.streamable_http_app()
    app.router.routes.insert(0, Route("/health", health))
    app.router.routes.insert(0, Route("/", health))
    if settings.mcp_token:
        app.add_middleware(BearerTokenMiddleware, token=settings.mcp_token)
    return app


def run_http(settings: Settings) -> None:
    import uvicorn

    app = build_http_app(settings)
    uvicorn.run(app, host=settings.mcp_host, port=settings.mcp_port, log_level="info")
