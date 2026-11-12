"""Application composition, lifecycle, static assets and browser security."""

from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import accounts, catalog, chat, experience
from .commerce import router as commerce_router
from .db import initialize
from .discovery import router as discovery_router
from .speech import router as speech_router

ROOT = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    initialize()
    yield


app = FastAPI(title="Mây Store · Local Demo", version="0.3.0", lifespan=lifespan)
for boundary in (accounts, catalog, chat, experience):
    app.include_router(boundary.router)
app.include_router(speech_router)
app.include_router(commerce_router)
app.include_router(discovery_router)
app.mount("/static", StaticFiles(directory=ROOT / "frontend"), name="static")
app.mount("/ami-assets", StaticFiles(directory=ROOT / "integrations" / "Ami-AI-Dev" / "public"), name="ami-assets")


@app.middleware("http")
async def browser_security(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    origin = request.headers.get("origin")
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and origin and origin != str(request.base_url).rstrip("/"):
        return Response("Cross-origin writes are not allowed", status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    if request.url.path == "/ami-assets/may-avatar.html":
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-eval'; img-src 'self' data: blob:; style-src 'self'; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'"
    elif request.url.path not in {"/docs", "/redoc", "/docs/oauth2-redirect"}:
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-src 'self' https://www.youtube.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    elif request.url.path == "/" or (request.url.path.startswith("/static/") and request.url.path.endswith((".js", ".css"))):
        # Revalidate application code so a backend update cannot reuse an incompatible client.
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "local-demo"}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(ROOT / "frontend" / "index.html")
