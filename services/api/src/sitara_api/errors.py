"""§34.4 error surface: every error leaving this service is the canonical
envelope from sitara_schemas — {code, message_key, trace_id, retryable} —
with HTTP status per the §6.3 convention. No module invents its own shape.
"""

import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sitara_schemas import ErrorCode, ErrorEnvelope
from sitara_schemas.errors import DEFAULT_RETRYABLE, HTTP_STATUS


class ApiError(Exception):
    """Raise anywhere below the router; the handler renders the envelope.

    `message_key` is an i18n key resolvable in every launch locale (§2.4) —
    it defaults to a per-code key but may be a more specific one.
    """

    def __init__(self, code: ErrorCode, message_key: str | None = None) -> None:
        self.code = code
        self.message_key = message_key or f"errors.{code.value.lower().replace('_', '.', 1)}"
        super().__init__(code.value)


def _envelope_response(code: ErrorCode, message_key: str) -> JSONResponse:
    envelope = ErrorEnvelope(
        code=code,
        message_key=message_key,
        trace_id=uuid.uuid4().hex,
        retryable=DEFAULT_RETRYABLE[code],
    )
    return JSONResponse(status_code=HTTP_STATUS[code], content=envelope.model_dump())


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _envelope_response(exc.code, exc.message_key)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_: Request, __: RequestValidationError) -> JSONResponse:
        return _envelope_response(ErrorCode.SYS_VALIDATION, "errors.sys.validation")

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, __: Exception) -> JSONResponse:
        return _envelope_response(ErrorCode.SYS_INTERNAL, "errors.sys.internal")
