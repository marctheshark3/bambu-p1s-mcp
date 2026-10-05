from __future__ import annotations

import hmac
import ipaddress
from contextlib import asynccontextmanager
from importlib.resources import files
from urllib.parse import urlsplit

from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Route
from starlette.types import ASGIApp

from bambu_p1s_mcp.camera import CameraError, close_camera, get_camera
from bambu_p1s_mcp.config import Settings
from bambu_p1s_mcp.redact import public_error, redact
from bambu_p1s_mcp.server import mcp

CAMERA_HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


def _is_loopback(host: str) -> bool:
    # Do not resolve hostnames: their addresses can change through DNS rebinding.
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower() == "localhost"


class LocalhostOnlyMiddleware(BaseHTTPMiddleware):
    """Protect token-free localhost listeners from browser DNS rebinding/CSRF."""

    async def dispatch(self, request: Request, call_next):
        hosts = request.headers.getlist("host")
        if len(hosts) != 1:
            return Response("invalid host", status_code=400)
        try:
            authority = urlsplit("//" + hosts[0])
            valid = (
                authority.netloc == hosts[0]
                and authority.username is None
                and authority.password is None
                and _is_loopback(authority.hostname or "")
                and (authority.port is None or authority.port > 0)
            )
        except ValueError:
            valid = False
        if not valid:
            return Response("invalid host", status_code=400)
        origins = request.headers.getlist("origin")
        if origins and origins != [f"{request.url.scheme}://{hosts[0]}"]:
            return Response("invalid origin", status_code=403)
        return await call_next(request)


class BearerTokenMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, token: str) -> None:
        super().__init__(app)
        self.token = token

    async def dispatch(self, request: Request, call_next):
        # The viewer shell contains no images or credentials. Its fetch requests
        # to /camera/* carry the same Authorization header as /mcp.
        if request.url.path in {"/health", "/", "/camera"}:
            return await call_next(request)
        header = request.headers.get("authorization", "")
        expected = f"Bearer {self.token}"
        if not hmac.compare_digest(header.encode(), expected.encode()):
            return Response("unauthorized", status_code=401)
        return await call_next(request)


async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "name": "bambu-p1s-mcp"})


def build_http_app(settings: Settings):
    # Only literal loopback addresses (or localhost) may run without a token.
    if not _is_loopback(settings.mcp_host) and not (settings.mcp_token and settings.mcp_token.strip()):
        raise ValueError(
            "BAMBU_MCP_TOKEN is required when HTTP listens outside localhost; "
            "set a server token or bind to 127.0.0.1 / ::1 and use an SSH tunnel"
        )
    # FastMCP already mounts Streamable HTTP at /mcp.
    app = mcp.streamable_http_app()

    async def camera_page(_request: Request) -> HTMLResponse:
        page = files("bambu_p1s_mcp").joinpath("camera.html").read_text(encoding="utf-8")
        page = page.replace("__AUTH_REQUIRED__", "true" if settings.mcp_token else "false")
        return HTMLResponse(page, headers={**CAMERA_HEADERS, "Referrer-Policy": "no-referrer"})

    def camera_error(exc: Exception) -> JSONResponse:
        message = redact(public_error(exc, settings.access_code), settings.mcp_token)
        return JSONResponse({"ok": False, "error": message}, status_code=503, headers=CAMERA_HEADERS)

    async def camera_snapshot(_request: Request) -> Response:
        try:
            frame = await run_in_threadpool(get_camera(settings).snapshot)
        except Exception as exc:
            return camera_error(exc)
        return Response(frame.jpeg, media_type="image/jpeg", headers=CAMERA_HEADERS)

    async def camera_stream(request: Request) -> Response:
        session = get_camera(settings)
        try:
            first = await run_in_threadpool(session.snapshot)
        except Exception as exc:
            return camera_error(exc)

        async def frames():
            frame = first
            try:
                while not await request.is_disconnected():
                    yield (
                        b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                        + str(len(frame.jpeg)).encode("ascii")
                        + b"\r\n\r\n" + frame.jpeg + b"\r\n"
                    )
                    frame = await run_in_threadpool(session.next_frame, frame.sequence)
            except CameraError:
                # Headers have already been sent. End the stream so viewers can
                # show disconnection and retry, rather than freezing silently.
                yield b"--frame--\r\n"

        return StreamingResponse(
            frames(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={**CAMERA_HEADERS, "X-Accel-Buffering": "no"},
        )

    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        try:
            async with original_lifespan(app) as state:
                yield state
        finally:
            await run_in_threadpool(close_camera)

    app.router.lifespan_context = lifespan
    app.router.routes[0:0] = [
        Route("/camera", camera_page),
        Route("/camera/snapshot.jpg", camera_snapshot),
        Route("/camera/stream.mjpg", camera_stream),
    ]
    app.router.routes.insert(0, Route("/health", health))
    app.router.routes.insert(0, Route("/", health))
    if settings.mcp_token:
        app.add_middleware(BearerTokenMiddleware, token=settings.mcp_token)
    else:
        app.add_middleware(LocalhostOnlyMiddleware)
    return app


def run_http(settings: Settings) -> None:
    import uvicorn

    app = build_http_app(settings)
    uvicorn.run(app, host=settings.mcp_host, port=settings.mcp_port, log_level="info")
