"""Aggregate optional API adapters used by interactive examples."""

from fastapi import APIRouter

from routers.chemistry_lab import router as chemistry_lab_router
from routers.magic_town import router as magic_town_router
from routers.live_science import router as live_science_router
from routers.math_garden import router as math_garden_router

router = APIRouter()
router.include_router(magic_town_router)
router.include_router(chemistry_lab_router)
router.include_router(live_science_router)
router.include_router(math_garden_router)
