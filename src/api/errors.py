"""Единый формат ошибок API.

Тело любой ошибки:
    {"error": {"code": "...", "message": "..."}, "request_id": "..."}
Traceback, пути файлов и внутренние сообщения клиенту не отдаются.
"""

import logging
from http import HTTPStatus

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("api.errors")


class ApiError(Exception):
    """Контролируемый отказ с HTTP-кодом и машинным кодом причины."""

    def __init__(self, status_code, code, message, headers=None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers


def get_request_id(request):
    return getattr(request.state, "request_id", None)


def error_response(request, status_code, code, message, headers=None):
    # причину отказа читает middleware для логов и метрик
    request.state.error_code = code

    return JSONResponse(
        status_code=status_code,
        content={
            "error": {"code": code, "message": message},
            "request_id": get_request_id(request),
        },
        headers=headers,
    )


async def _api_error(request, exc):
    return error_response(
        request, exc.status_code, exc.code, exc.message, exc.headers
    )


async def _http_error(request, exc):
    # 404, 405 и т.п. от маршрутизатора: стандартная фраза вместо detail
    phrase = HTTPStatus(exc.status_code).phrase
    return error_response(
        request, exc.status_code, f"http_{exc.status_code}", phrase,
        getattr(exc, "headers", None),
    )


async def _validation_error(request, exc):
    return error_response(request, 422, "invalid_input", "Некорректный вход.")


async def _unhandled_error(request, exc):
    # traceback только в лог сервера, клиенту — общее сообщение
    logger.exception(
        "unhandled_error", extra={"fields": {"request_id": get_request_id(request)}}
    )
    return error_response(request, 500, "internal_error", "Внутренняя ошибка.")


def install_error_handlers(app):
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled_error)
