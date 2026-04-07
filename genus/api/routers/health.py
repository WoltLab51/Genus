"""
GET /health

Liveness-check endpoint — no authentication required.
Response: {"status": "ok", "version": "1.0.0"}
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from genus.api._version import API_VERSION

router = APIRouter()


@router.get("/health")
async def health() -> JSONResponse:
    """Return API liveness status."""
    return JSONResponse({"status": "ok", "version": API_VERSION})
