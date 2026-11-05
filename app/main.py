"""FastAPI application entrypoint for the helpdesk service."""

from fastapi import FastAPI

app = FastAPI(
    title="Helpdesk Service",
    description="AI-powered helpdesk assistant backed by a knowledge base of SaaS product articles.",
    version="0.1.0",
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Return service liveness status (must respond with 200 OK)."""
    return {"status": "ok"}
