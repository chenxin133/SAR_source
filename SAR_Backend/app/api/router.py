from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import annotations, health, images, imports, samples, storage, tasks, tiff_compat


api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(images.router, prefix="/images", tags=["images"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(samples.router, prefix="/samples", tags=["samples"])
api_router.include_router(annotations.router, prefix="/annotations", tags=["annotations"])
api_router.include_router(imports.router, prefix="/imports", tags=["imports"])
api_router.include_router(storage.router, prefix="/storage", tags=["storage"])

api_router.include_router(tiff_compat.router, prefix="/tiff", tags=["tiff-compat"])
