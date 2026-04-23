"""
GENUS API — FastAPI App Factory

Design principles:
- App-Factory pattern: create_app() returns a configured FastAPI instance.
- Lifespan context: MessageBus and agents are started/stopped cleanly.
- API-Key auth via middleware (Reader endpoints exempt).
- No business logic here — only wiring.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from genus.api._version import API_VERSION
from genus.api.errors import ErrorHandlingMiddleware
from genus.api.middleware import ApiKeyMiddleware
from genus.api.routers import health, outcome, runs
from genus.api.routers import kill_switch as kill_switch_router
from genus.api.routes import agents as agents_router
from genus.api.routes import chat as chat_router
from genus.api.routes import chat_rest as chat_rest_router
from genus.api.routes import builder as builder_router
from genus.api.routes import devloop as devloop_router
from genus.api.routes import identity as identity_router
from genus.api.routes import memory as memory_router
from genus.identity.actor_registry import build_actor_registry


def create_app(
    *,
    api_key: str = "",
    admin_key: str = "",
    operator_key: str = "",
    reader_key: str = "",
    message_bus=None,
    kill_switch=None,
    run_store=None,
    use_lifespan: bool = False,
) -> FastAPI:
    """Create and configure the GENUS FastAPI application.

    Args:
        api_key:       Legacy single-key mode.  When set (and admin_key/operator_key
                       are not), ``api_key`` is treated as an admin key so it gains
                       all permissions.  Existing callers that pass only ``api_key``
                       continue to work without any changes.
        admin_key:     Key with admin role (activate/deactivate kill-switch).
        operator_key:  Key with operator role (start runs).
        reader_key:    Key with reader role (read-only GET endpoints).
        message_bus:   Injected MessageBus (for tests). If None and use_lifespan=False, bus is None.
        kill_switch:   Injected KillSwitch (for tests).
        run_store:     Injected JsonlRunStore (for tests). If None, deps.py creates a default instance.
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

    # Backward compat: a lone api_key becomes the admin key (admin darf alles).
    if api_key and not admin_key and not operator_key:
        _admin_key = api_key
        _operator_key = ""
        _reader_key = reader_key
    else:
        _admin_key = admin_key
        _operator_key = operator_key
        _reader_key = reader_key

    actor_registry = build_actor_registry(
        admin_key=_admin_key,
        operator_key=_operator_key,
        reader_key=_reader_key,
    )

    app = FastAPI(
        title="GENUS API",
        version=API_VERSION,
        description="GENUS-2.0 external interface",
        lifespan=lifespan,
    )

    # Store dependencies in app state
    app.state.message_bus = message_bus
    app.state.kill_switch = kill_switch
    app.state.run_store = run_store
    app.state.actor_registry = actor_registry
    # Set of all valid API keys for inline WS auth
    app.state.api_keys = actor_registry.api_keys

    # Middleware (order matters: errors outermost)
    app.add_middleware(ErrorHandlingMiddleware)
    app.add_middleware(
        ApiKeyMiddleware,
        actor_registry=actor_registry,
    )

    # Routers
    app.include_router(health.router)
    app.include_router(runs.router, prefix="/runs")
    app.include_router(outcome.router, prefix="/outcome")
    app.include_router(kill_switch_router.router, prefix="/kill-switch")
    app.include_router(chat_router.router, tags=["chat"])
    app.include_router(chat_rest_router.router, tags=["chat"])
    app.include_router(builder_router.router, tags=["builder"])
    app.include_router(devloop_router.router, tags=["devloop"])
    app.include_router(identity_router.router, tags=["identity"])
    app.include_router(memory_router.router, tags=["memory"])
    app.include_router(agents_router.router, tags=["agents"])

    # v1 prefix aliases — make legacy endpoints also reachable under /v1/
    # Kill-switch already has its own /v1/admin/kill-switch path in addition.
    app.include_router(runs.router, prefix="/v1/runs", include_in_schema=False)
    app.include_router(outcome.router, prefix="/v1/outcome", include_in_schema=False)
    app.include_router(
        kill_switch_router.router,
        prefix="/v1/admin/kill-switch",
        tags=["admin"],
    )

    # UI: served from genus/ui/index.html.
    # Mount happens LAST so all API routes take priority.
    # Exempt from auth middleware via EXEMPT_PATHS (see middleware.py).
    _ui_dir = Path(__file__).parent.parent / "ui"
    if _ui_dir.is_dir():
        _static_dir = _ui_dir / "static"
        if _static_dir.is_dir():
            app.mount("/static", StaticFiles(directory=_static_dir), name="static")

        @app.get("/", include_in_schema=False)
        async def serve_ui() -> FileResponse:
            """Serve the GENUS Chat UI."""
            return FileResponse(_ui_dir / "index.html")

    return app
