"""
Watchlist package initialization.
Merges core POI identity endpoints with CCTNS hot-list registries.
"""
from fastapi import APIRouter
from .matcher import check_plate_against_stolen_watchlist, check_face_against_person_watchlist
from .core_router import router as core_watchlist_router
from .router import router as cctns_watchlist_router

# Unified Watchlist Router mounted at /api/v1/watchlist
router = APIRouter(prefix="/watchlist", tags=["Watchlist"])
router.include_router(core_watchlist_router)
router.include_router(cctns_watchlist_router)

__all__ = [
    "check_plate_against_stolen_watchlist",
    "check_face_against_person_watchlist",
    "router",
]
