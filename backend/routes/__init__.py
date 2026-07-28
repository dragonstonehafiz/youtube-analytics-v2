from __future__ import annotations

from fastapi import APIRouter

from .analytics import router as analytics_router
from .metadata import router as metadata_router
from .playlists import router as playlists_router
from .synchronization import router as synchronization_router
from .videos import router as videos_router

router = APIRouter()
router.include_router(videos_router)
router.include_router(playlists_router)
router.include_router(analytics_router)
router.include_router(synchronization_router)
router.include_router(metadata_router)

__all__ = ["router"]
