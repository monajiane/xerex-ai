"""Typed application errors and the uniform error envelope.

The API never returns Persian text (PROMPT.md section 4). It returns a stable
English ``error.code``; the Persian admin panel maps that code to a Persian
message through ``frontend/src/i18n``.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger, request_id_ctx

logger = get_logger(__name__)


class AppError(Exception):
    """Base class for every expected, typed failure."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"
    message: str = "The request could not be processed."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details or {}
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "The requested resource does not exist."


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    message = "The resource already exists or conflicts with the current state."


class ValidationError(AppError):
    status_code = 422
    code = "validation_failed"
    message = "The submitted data is invalid."


class AuthenticationError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "authentication_failed"
    message = "Authentication failed."


class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "permission_denied"
    message = "The authenticated account is not allowed to perform this action."


class RateLimitedError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limit_exceeded"
    message = "Too many requests."


class BootstrapClosedError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "bootstrap_closed"
    message = "Initial setup has already been completed."


class DependencyUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "dependency_unavailable"
    message = "A required dependency is unavailable."


class NotImplementedYetError(AppError):
    status_code = status.HTTP_501_NOT_IMPLEMENTED
    code = "not_implemented"
    message = "This capability is planned for a later milestone."


def _envelope(code: str, message: str, *, details: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id_ctx.get() or None,
        }
    }
    if details:
        payload["error"]["details"] = details
    return payload


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error("application_error", extra={"code": exc.code, "detail": exc.message})
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, details=exc.details or None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {
                "location": ".".join(str(part) for part in error.get("loc", ())),
                "type": error.get("type", "invalid"),
                "message": error.get("msg", "Invalid value."),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_envelope(
                "request_validation_failed",
                "One or more request fields are invalid.",
                details={"fields": fields},
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {
            401: "authentication_required",
            403: "permission_denied",
            404: "route_not_found",
            405: "method_not_allowed",
            409: "conflict",
            429: "rate_limit_exceeded",
        }
        code = codes.get(exc.status_code, "http_error")
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(code, str(exc.detail)),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", extra={"error_type": type(exc).__name__})
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope("internal_error", "An unexpected error occurred."),
        )
