"""Health check router."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Return service liveness status (must respond with 200 OK)."""
    return {"status": "ok"}
