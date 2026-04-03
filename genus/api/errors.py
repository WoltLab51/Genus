"""Error handling middleware and utilities."""

import logging
import traceback
from typing import Any, Dict

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for centralized error handling.

    Catches all exceptions and returns structured JSON responses.
    """

    async def dispatch(self, request: Request, call_next):
        """
        Process request and handle errors.

        Args:
            request: The incoming request
            call_next: Next middleware/handler in chain

        Returns:
            Response with error details if an exception occurred
        """
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            logger.error(
                f"Error processing request {request.method} {request.url.path}: {e}",
                exc_info=True
            )

            error_response: Dict[str, Any] = {
                "error": type(e).__name__,
                "message": str(e),
                "path": request.url.path,
                "method": request.method
            }

            # Add traceback in debug mode
            if hasattr(request.app.state, "config") and request.app.state.config.debug:
                error_response["traceback"] = traceback.format_exc()

            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=error_response
            )
