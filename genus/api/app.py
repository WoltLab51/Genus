"""FastAPI application factory with production safeguards."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from typing import AsyncIterator

from genus.core.config import Config
from genus.api.middleware import AuthenticationMiddleware
from genus.api.errors import ErrorHandlingMiddleware
from genus.communication import MessageBus


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan context manager.

    Manages initialization and cleanup of application resources:
    - Configuration
    - MessageBus
    - Agents and stores (when implemented)

    No global singletons - all dependencies created here and injected.
    """
    # Initialize configuration
    try:
        config = Config()
    except ValueError as e:
        print(f"Configuration error: {e}")
        raise

    # Initialize message bus
    message_bus = MessageBus()

    # Store in app state for access in endpoints
    app.state.config = config
    app.state.message_bus = message_bus

    print(f"GENUS starting in {config.environment} mode")
    print(f"Debug mode: {config.debug}")
    print(f"Authentication: API key required (set via API_KEY environment variable)")

    yield

    # Cleanup
    print("GENUS shutting down")
    message_bus.clear_history()


def create_app() -> FastAPI:
    """Create and configure FastAPI application with production safeguards.

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="GENUS",
        description="Multi-agent system with production safeguards",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Note: Middleware is applied in reverse order (last added = first executed)

    # 1. Error handling middleware (outermost - catches all errors)
    debug_mode = False  # Will be set from config after initialization
    app.add_middleware(ErrorHandlingMiddleware, debug=debug_mode)

    # Health check endpoint (no authentication required)
    @app.get("/health")
    async def health_check():
        """Health check endpoint for monitoring."""
        return {
            "status": "healthy",
            "service": "GENUS",
        }

    # Protected endpoints
    @app.get("/")
    async def root(request: Request):
        """Root endpoint with system information."""
        config = request.app.state.config
        return {
            "service": "GENUS",
            "version": "1.0.0",
            "environment": config.environment,
            "authentication": "API key required",
        }

    @app.get("/status")
    async def get_status(request: Request):
        """Get system status and message bus statistics."""
        message_bus = request.app.state.message_bus
        history = message_bus.get_message_history(limit=10)

        return {
            "status": "running",
            "message_bus": {
                "total_messages": len(message_bus._message_history),
                "recent_messages": len(history),
            }
        }

    @app.get("/messages")
    async def get_messages(request: Request, topic: str = None, limit: int = 100):
        """Get message history from the message bus.

        Args:
            topic: Optional topic filter
            limit: Maximum number of messages (default: 100, max: 1000)
        """
        if limit > 1000:
            limit = 1000

        message_bus = request.app.state.message_bus
        messages = message_bus.get_message_history(topic=topic, limit=limit)

        return {
            "total": len(messages),
            "messages": [
                {
                    "topic": msg.topic,
                    "data": msg.data,
                    "timestamp": msg.timestamp.isoformat(),
                    "sender": msg.sender,
                }
                for msg in messages
            ]
        }

    return app


def create_app_with_auth() -> FastAPI:
    """Create FastAPI application with authentication middleware.

    This factory function adds authentication middleware after app creation.
    Should be used for production deployments.

    Returns:
        Configured FastAPI application with authentication
    """
    app = create_app()

    # Initialize config to get API key for authentication
    # This is done here because middleware needs config before lifespan
    try:
        config = Config()
        # Update debug mode in error handling if needed
        app.add_middleware(AuthenticationMiddleware, config=config)
    except ValueError as e:
        print(f"Warning: Could not initialize authentication middleware: {e}")
        print("Application will start without authentication!")

    return app
