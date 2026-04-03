"""Error handling utilities for detailed error responses."""
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable
import traceback
import sys


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware to handle errors and provide detailed error responses."""

    def __init__(self, app, debug: bool = False):
        """Initialize error handling middleware.

        Args:
            app: FastAPI application
            debug: Whether to include detailed error information
        """
        super().__init__(app)
        self.debug = debug

    async def dispatch(self, request: Request, call_next: Callable):
        """Process request and handle any errors.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware in chain

        Returns:
            HTTP response
        """
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            return self._create_error_response(exc, request)

    def _create_error_response(self, exc: Exception, request: Request) -> JSONResponse:
        """Create detailed error response.

        Args:
            exc: Exception that occurred
            request: Request that caused the error

        Returns:
            JSON response with error details
        """
        error_type = type(exc).__name__
        error_message = str(exc)

        # Build error response
        error_data = {
            "error": error_type,
            "message": error_message or "An unexpected error occurred",
            "path": request.url.path,
            "method": request.method,
        }

        # Add detailed information in debug mode
        if self.debug:
            error_data["details"] = {
                "traceback": traceback.format_exception(
                    type(exc), exc, exc.__traceback__
                ),
                "exception_module": exc.__class__.__module__,
            }

        # Determine status code based on exception type
        status_code = self._determine_status_code(exc)

        return JSONResponse(
            status_code=status_code,
            content=error_data,
        )

    @staticmethod
    def _determine_status_code(exc: Exception) -> int:
        """Determine appropriate HTTP status code for exception.

        Args:
            exc: Exception that occurred

        Returns:
            HTTP status code
        """
        # Map common exception types to status codes
        if isinstance(exc, ValueError):
            return status.HTTP_400_BAD_REQUEST
        elif isinstance(exc, KeyError):
            return status.HTTP_404_NOT_FOUND
        elif isinstance(exc, PermissionError):
            return status.HTTP_403_FORBIDDEN
        else:
            return status.HTTP_500_INTERNAL_SERVER_ERROR
