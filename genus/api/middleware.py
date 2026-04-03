"""Authentication middleware for API key validation."""
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable, Optional

from genus.core.config import Config


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce API key authentication on all requests."""

    def __init__(self, app, config: Config):
        """Initialize authentication middleware.

        Args:
            app: FastAPI application
            config: Application configuration with API key
        """
        super().__init__(app)
        self.config = config

    async def dispatch(self, request: Request, call_next: Callable):
        """Process request and validate authentication.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware in chain

        Returns:
            HTTP response

        Raises:
            HTTPException: If authentication fails
        """
        # Skip authentication for health check endpoint
        if request.url.path == "/health":
            return await call_next(request)

        # Extract API key from Authorization header
        auth_header = request.headers.get("Authorization")
        api_key = self._extract_api_key(auth_header)

        # Validate API key
        if not self.config.validate_api_key(api_key):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error": "Unauthorized",
                    "message": "Invalid or missing API key. Please provide a valid API key in the Authorization header as 'Bearer <API_KEY>'.",
                    "details": {
                        "expected_header": "Authorization: Bearer <API_KEY>",
                        "received_header": "Authorization: Bearer ***" if api_key else "None"
                    }
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Continue to next middleware/endpoint
        return await call_next(request)

    @staticmethod
    def _extract_api_key(auth_header: Optional[str]) -> Optional[str]:
        """Extract API key from Authorization header.

        Args:
            auth_header: Authorization header value

        Returns:
            API key if present and properly formatted, None otherwise
        """
        if auth_header is None:
            return None

        # Expected format: "Bearer <API_KEY>"
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None

        return parts[1]
