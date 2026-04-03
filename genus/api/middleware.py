"""Authentication and authorization middleware."""

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from genus.core.config import Config


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware for API key authentication.

    All endpoints except /health require authentication.
    """

    def __init__(self, app, config: Config):
        """Initialize auth middleware.

        Args:
            app: FastAPI application
            config: Application configuration
        """
        super().__init__(app)
        self.config = config

    async def dispatch(self, request: Request, call_next):
        """Process request and verify authentication.

        Args:
            request: Incoming request
            call_next: Next middleware/handler

        Returns:
            Response from handler or 401 error

        Raises:
            HTTPException: If authentication fails
        """
        # Skip auth for health endpoint
        if request.url.path == "/health":
            return await call_next(request)

        # Check for API key in Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

        api_key = auth_header.replace("Bearer ", "")
        if api_key != self.config.api_key:
            raise HTTPException(status_code=401, detail="Invalid API key")

        return await call_next(request)
