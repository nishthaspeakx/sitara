"""§34.4 error surface: every error leaving this service is the canonical
envelope from sitara_schemas — {code, message_key, trace_id, retryable} —
with HTTP status per the §6.3 convention. No module invents its own shape.
"""

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sitara_schemas import ErrorCode, ErrorEnvelope
from sitara_schemas.errors import DEFAULT_RETRYABLE, HTTP_STATUS

logger = logging.getLogger(__name__)


class AstroError(Exception):
    """Raise anywhere below the router; the handler renders the envelope.

    `detail` is for operators, never for users and never for the wire — it must
    already be PII-free (§13: use sitara_astro.pii.redact on any user value).
    """

    def __init__(
        self, code: ErrorCode, message_key: str | None = None, detail: str | None = None
    ) -> None:
        self.code = code
        self.message_key = message_key or f"errors.{code.value.lower().replace('_', '.', 1)}"
        self.detail = detail
        super().__init__(f"{code.value}: {detail}" if detail else code.value)


def _envelope_response(
    code: ErrorCode, message_key: str, trace_id: str | None = None
) -> JSONResponse:
    envelope = ErrorEnvelope(
        code=code,
        message_key=message_key,
        trace_id=trace_id or uuid.uuid4().hex,
        retryable=DEFAULT_RETRYABLE[code],
    )
    return JSONResponse(status_code=HTTP_STATUS[code], content=envelope.model_dump())


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AstroError)
    async def handle_astro_error(_: Request, exc: AstroError) -> JSONResponse:
        return _envelope_response(exc.code, exc.message_key)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_: Request, __: RequestValidationError) -> JSONResponse:
        return _envelope_response(ErrorCode.SYS_VALIDATION, "errors.sys.validation")

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Traceback only — never the request body (birth data is PII, §13).
        trace_id = uuid.uuid4().hex
        logger.exception("unhandled error trace_id=%s", trace_id, exc_info=exc)
        return _envelope_response(ErrorCode.SYS_INTERNAL, "errors.sys.internal", trace_id)
