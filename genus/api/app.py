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
from genus.api.routes import chat as chat_router
from genus.api.routes import chat_rest as chat_rest_router
from genus.api.routes import identity as identity_router


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
    # Set of all valid API keys for inline WS auth
    app.state.api_keys = {k for k in [_admin_key, _operator_key, _reader_key] if k}

    # Middleware (order matters: errors outermost)
    app.add_middleware(ErrorHandlingMiddleware)
    app.add_middleware(
        ApiKeyMiddleware,
        admin_key=_admin_key,
        operator_key=_operator_key,
        reader_key=_reader_key,
    )

    # Routers
    app.include_router(health.router)
    app.include_router(runs.router, prefix="/runs")
    app.include_router(outcome.router, prefix="/outcome")
    app.include_router(kill_switch_router.router, prefix="/kill-switch")
    app.include_router(chat_router.router, tags=["chat"])
    app.include_router(chat_rest_router.router, tags=["chat"])
    app.include_router(identity_router.router, tags=["identity"])

    return app
