"""TiendaDemo: dummy e-commerce app used as the target of the QA agent lab."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.routers import api, pages

app = FastAPI(
    title="TiendaDemo",
    description="App dummie del Laboratorio QA: e-commerce con defectos sembrados activables.",
    version="0.1.0",
)

app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(pages.router)
app.include_router(api.router)


@app.exception_handler(404)
async def not_found(request: Request, exc):
    templates = Jinja2Templates(directory=BASE_DIR / "templates")
    return templates.TemplateResponse(
        request, "404.html", {"request": request}, status_code=404
    )


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok", "app": settings.app_name}
