"""
Error handling middleware for GENUS API.
"""
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import logging
import traceback

logger = logging.getLogger(__name__)


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to catch all errors and return structured JSON.
    All errors are caught and returned as JSON with error type, message, path, and method.
    Debug mode adds traceback details.
    HTTPException is re-raised to be handled by FastAPI's default handler.
    """

    def __init__(self, app, debug: bool = False):
        super().__init__(app)
        self.debug = debug

    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except HTTPException:
            # Re-raise HTTPException to be handled by FastAPI's default handler
            raise
        except Exception as exc:
            logger.error(
                f"Error processing request {request.method} {request.url.path}: {exc}"
            )

            error_response = {
                "error": type(exc).__name__,
                "message": str(exc),
                "path": str(request.url.path),
                "method": request.method,
            }

            if self.debug:
                error_response["traceback"] = traceback.format_exc()

            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=error_response,
            )
