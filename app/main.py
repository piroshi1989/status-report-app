"""FastAPI アプリ本体."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import config, db
from .routers import criteria, home, patients, pdf_router, report, upload


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()  # スキーマ作成 + 初回シード
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="状況報告書作成アプリ", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(config.static_dir())), name="static")
    app.include_router(home.router)
    app.include_router(patients.router)
    app.include_router(upload.router)
    app.include_router(report.router)
    app.include_router(criteria.router)
    app.include_router(pdf_router.router)
    return app


app = create_app()
