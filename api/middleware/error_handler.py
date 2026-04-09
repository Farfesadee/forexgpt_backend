
"""
api/middleware/error_handler.py — Global exception handlers.

Catches unhandled exceptions and Supabase API errors and returns
consistent JSON error responses. Registered in main.py.
"""

import logging
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from httpx import HTTPStatusError
from services.ai_errors import AIServiceUnavailableError

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    """Register all global error handlers on the FastAPI app instance."""

    @app.exception_handler(AIServiceUnavailableError)
    async def ai_service_unavailable_handler(request: Request, exc: AIServiceUnavailableError):
        """Return a consistent 503 response for temporary upstream AI outages."""
        logger.warning(f"AI service unavailable on {request.url}: {exc}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": str(exc),
                "error_type": "ai_service_unavailable",
                "retry_after": exc.retry_after_seconds,
            },
            headers={"Retry-After": str(exc.retry_after_seconds)},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        """Return 422 with human-readable field errors."""
        errors = []
        for err in exc.errors():
            field = " → ".join(str(loc) for loc in err["loc"] if loc != "body")
            errors.append({"field": field or "request", "message": err["msg"]})
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": "Validation error", "errors": errors},
        )

    @app.exception_handler(HTTPStatusError)
    async def supabase_http_error_handler(request: Request, exc: HTTPStatusError):
        """Translate Supabase HTTP errors into consistent API responses."""
        code = exc.response.status_code
        try:
            body = exc.response.json()
            message = body.get("error_description") or body.get("msg") or body.get("message") or str(exc)
        except Exception:
            message = str(exc)

        logger.warning(f"Supabase HTTP {code}: {message} | {request.url}")

        # Map Supabase error codes to meaningful messages
        if code == 400 and "invalid" in message.lower():
            return JSONResponse(status_code=400, content={"detail": message})
        if code == 401:
            return JSONResponse(status_code=401, content={"detail": "Invalid credentials or session expired."})
        if code == 422:
            return JSONResponse(status_code=422, content={"detail": message})
        if code == 429:
            return JSONResponse(status_code=429, content={"detail": "Too many requests. Please try again later."})

        return JSONResponse(status_code=502, content={"detail": "Auth service error. Please try again."})

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        """Catch-all for unhandled exceptions — never leak stack traces to clients."""
        logger.error(f"Unhandled exception on {request.url}: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An unexpected error occurred. Please try again."},
        )
