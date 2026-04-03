"""Error handling middleware."""

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import traceback


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware for structured error handling."""

    def __init__(self, app, debug: bool = False):
        """Initialize error handling middleware.

        Args:
            app: FastAPI application
            debug: Whether to include traceback in responses
        """
        super().__init__(app)
        self.debug = debug

    async def dispatch(self, request: Request, call_next):
        """Process request with error handling.

        Args:
            request: Incoming request
            call_next: Next middleware/handler

        Returns:
            Response or structured error
        """
        try:
            return await call_next(request)
        except Exception as e:
            error_response = {
                "error": type(e).__name__,
                "message": str(e),
                "path": request.url.path,
                "method": request.method,
            }

            if self.debug:
                error_response["traceback"] = traceback.format_exc()

            return JSONResponse(
                status_code=500,
                content=error_response
            )
