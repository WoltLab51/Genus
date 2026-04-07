"""
GENUS API — FastAPI App Factory

Design principles:
- App-Factory pattern: create_app() returns a configured FastAPI instance.
- Lifespan context: MessageBus and agents are started/stopped cleanly.
- API-Key auth via middleware (Reader endpoints exempt).
- No business logic here — only wiring.
"""

from fastapi import FastAPI

from genus.api._version import API_VERSION
from genus.api.errors import ErrorHandlingMiddleware
from genus.api.middleware import ApiKeyMiddleware
from genus.api.routers import health, outcome, runs


def create_app(*, api_key: str, message_bus=None) -> FastAPI:
    """Create and configure the GENUS FastAPI application.

    Args:
        api_key:     The API key required for Operator/Admin endpoints.
        message_bus: Optional MessageBus instance (injected for testing).

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(
        title="GENUS API",
        version=API_VERSION,
        description="GENUS-2.0 external interface",
    )

    # Store dependencies in app state
    app.state.api_key = api_key
    app.state.message_bus = message_bus

    # Middleware (order matters: errors outermost)
    app.add_middleware(ErrorHandlingMiddleware)
    app.add_middleware(ApiKeyMiddleware, api_key=api_key)

    # Routers
    app.include_router(health.router)
    app.include_router(runs.router, prefix="/runs")
    app.include_router(outcome.router, prefix="/outcome")

    return app
