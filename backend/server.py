from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import database
import sync
from logging_config import exception_context, get_logger
from routes import router

_logger = get_logger("lifecycle")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _logger.info("Application startup")
    try:
        # Only the startup work is wrapped by the inner handler, so the ERROR record
        # cannot misattribute a later runtime failure to startup. The outer finally still
        # emits shutdown in every case, so teardown after a failed startup stays visible.
        try:
            database.init_db()
            sync.start_background_scheduler()
        except Exception as exc:
            _logger.error("Application startup failed %s", exception_context(exc))
            raise
        yield
    finally:
        _logger.info("Application shutdown")


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000)
