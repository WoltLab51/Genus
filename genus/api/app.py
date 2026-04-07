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
from genus.api.routers import kill_switch as kill_switch_router


def create_app(*, api_key: str, message_bus=None, kill_switch=None, use_lifespan: bool = False) -> FastAPI:
    """Create and configure the GENUS FastAPI application.

    Args:
        api_key:       Required API key for Bearer authentication.
        message_bus:   Injected MessageBus (for tests). If None and use_lifespan=False, bus is None.
        kill_switch:   Injected KillSwitch (for tests).
        use_lifespan:  If True, use genus_lifespan for production startup.
                       If False (default), no automatic agent startup (test mode).

    Returns:
        Configured FastAPI application.
    """
    if use_lifespan:
        from genus.api.lifespan import genus_lifespan
        lifespan = genus_lifespan
    else:
        lifespan = None

    app = FastAPI(
        title="GENUS API",
        version=API_VERSION,
        description="GENUS-2.0 external interface",
        lifespan=lifespan,
    )

    # Store dependencies in app state
    app.state.api_key = api_key
    app.state.message_bus = message_bus
    app.state.kill_switch = kill_switch

    # Middleware (order matters: errors outermost)
    app.add_middleware(ErrorHandlingMiddleware)
    app.add_middleware(ApiKeyMiddleware, api_key=api_key)

    # Routers
    app.include_router(health.router)
    app.include_router(runs.router, prefix="/runs")
    app.include_router(outcome.router, prefix="/outcome")
    app.include_router(kill_switch_router.router, prefix="/kill-switch")

    return app
