"""
PAALS — Process-Aware Agentic Loop for Supply Chain Oversight
Main application entry point.
"""
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, Response

import aiosqlite

from app.models.database import init_db, DB_PATH
from app.services.seed import seed_database
from app.services.kaggle_import import import_dataco
from app.services.scms_import import import_scms
from app.services.websocket import manager, event_broadcaster
from app.routes.api import router as api_router, kaggle_insights, scms_insights

# Resolve paths relative to this file so the app works from any cwd
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "app", "templates")
STATIC_DIR = os.path.join(BASE_DIR, "app", "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await seed_database()
    # Kaggle imports (first run only: DataCo ~30s, SCMS ~4s) run off the event loop, one after
    # the other so they never compete for the SQLite write lock; then the dashboard's chart
    # data is pre-computed so the first visitor doesn't wait ~3s for it
    async def import_then_warm():
        await asyncio.to_thread(lambda: (import_dataco(), import_scms()))
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            await kaggle_insights(db)
            await scms_insights(db)
    asyncio.create_task(import_then_warm())
    asyncio.create_task(event_broadcaster())
    yield


app = FastAPI(
    title="PAALS — Supply Chain Oversight",
    description="Process-Aware Agentic Loop for autonomous supply chain oversight",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def asset(path: str) -> str:
    """Static URL with a version stamp from the file's mtime, so an edited CSS/JS file gets a new
    URL and browsers can never pair a new page with an old cached script."""
    try:
        version = int(os.path.getmtime(os.path.join(STATIC_DIR, path)))
    except OSError:
        version = 0
    return f"/static/{path}?v={version}"


templates.env.globals["asset"] = asset


@app.middleware("http")
async def static_revalidate(request: Request, call_next):
    # Without Cache-Control, browsers guess how long to reuse static files and can serve stale JS.
    # no-cache keeps them cached but revalidates with the ETag every time (a cheap 304 when unchanged).
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.include_router(api_router)


# ── Favicon ──────────────────────────────────────────────────────────────────

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="4" fill="#f3eee4"/><text x="4" y="24" font-size="22" fill="#2d4a6b">&#x25C8;</text></svg>'
    return Response(content=svg, media_type="image/svg+xml")


# ── Page routes ──────────────────────────────────────────────────────────────
# Starlette ≥ 1.0 signature: TemplateResponse(request, name, context=None)

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")


@app.get("/deviations", response_class=HTMLResponse)
async def deviations_page(request: Request):
    return templates.TemplateResponse(request, "deviations.html")


@app.get("/deviations/{dev_id}", response_class=HTMLResponse)
async def deviation_detail(request: Request, dev_id: str):
    return templates.TemplateResponse(request, "deviation_detail.html", {"dev_id": dev_id})


@app.get("/action-centre", response_class=HTMLResponse)
async def action_centre(request: Request):
    return templates.TemplateResponse(request, "action_centre.html")


@app.get("/digital-twin", response_class=HTMLResponse)
async def digital_twin(request: Request):
    return templates.TemplateResponse(request, "digital_twin.html")


@app.get("/research", response_class=HTMLResponse)
async def research(request: Request):
    return templates.TemplateResponse(request, "research.html")


@app.get("/suppliers", response_class=HTMLResponse)
async def suppliers_page(request: Request):
    return templates.TemplateResponse(request, "suppliers.html")


@app.get("/purchase-orders", response_class=HTMLResponse)
async def purchase_orders_page(request: Request):
    return templates.TemplateResponse(request, "purchase_orders.html")


# ── WebSocket ────────────────────────────────────────────────────────────────

@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # keep-alive ping from client; we don't parse the payload
            await asyncio.wait_for(websocket.receive_text(), timeout=30)
    except (WebSocketDisconnect, asyncio.TimeoutError):
        manager.disconnect(websocket)
