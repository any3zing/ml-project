"""HTTP API классификатора prompt injection (ЛР4).

Запуск из корня репозитория:
    API_TOKEN_FILE=... METRICS_TOKEN_FILE=... \\
    uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --no-proxy-headers
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from src.api.errors import ApiError, error_response, install_error_handlers
from src.api.limits import InferenceLimiter
from src.api.model_service import ModelNotReadyError, ModelService
from src.api.observability import (
    Metrics,
    method_label,
    outcome_of,
    route_label,
    setup_logging,
)
from src.api.security import MIN_TOKEN_LENGTH, Guard, require_metrics_token
from src.api.settings import Settings
from src.api.validation import read_json_payload
from src.paths import PROJECT_ROOT
from src.predict import (
    InputValidationError,
    PredictionUnavailableError,
    validate_input,
)

setup_logging()
logger = logging.getLogger("api.app")
request_logger = logging.getLogger("api.request")

# Код причины из validate_input -> HTTP-статус (остальные — 422)
VALIDATION_STATUS = {"text_too_long": 413}
LOG_LEVELS = {"ok": logging.INFO, "rejected": logging.WARNING, "error": logging.ERROR}

STATIC_DIR = PROJECT_ROOT / "static"

# Заголовки безопасности для всех ответов: страница и API на одном origin,
# CORS не настраивается
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; base-uri 'none'; form-action 'none'; "
        "frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def create_app(settings=None):
    settings = settings or Settings.from_env()
    service = ModelService(settings)
    limiter = InferenceLimiter(
        settings.max_concurrent, settings.queue_timeout, settings.inference_timeout
    )
    guard = Guard(settings)
    metrics = Metrics(settings.model_version)
    token = settings.metrics_token
    metrics_token = token if token and len(token) >= MIN_TOKEN_LENGTH else None

    def is_ready():
        # готов = модель загружена и проверена + задан серверный токен
        return service.ready and guard.configured

    @asynccontextmanager
    async def lifespan(app):
        # Модель загружается один раз при старте, до приёма запросов
        service.load()
        if guard.problem:
            logging.getLogger("api.auth").error(
                "not_ready", extra={"fields": {"reason": guard.problem}}
            )
        if metrics_token is None:
            logger.warning(
                "metrics_disabled",
                extra={"fields": {"reason": "metrics_token_missing_or_short"}},
            )
        metrics.model_ready.set(1 if is_ready() else 0)
        yield

    app = FastAPI(
        title="Prompt injection classifier",
        version=settings.model_version,
        lifespan=lifespan,
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.enable_docs else None,
    )
    app.state.model_service = service
    app.state.guard = guard
    app.state.metrics = metrics
    install_error_handlers(app)

    @app.middleware("http")
    async def observe_request(request: Request, call_next):
        # Идентификатор всегда генерирует сервер; клиентский не принимается
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # traceback клиенту не отдаётся; в лог — только тип исключения
            logger.exception(
                "unhandled_error", extra={"fields": {"request_id": request_id}}
            )
            response = error_response(
                request, 500, "internal_error", "Внутренняя ошибка."
            )
        duration = time.perf_counter() - started

        route = route_label(request.url.path)
        method = method_label(request.method)
        status = response.status_code
        outcome, reason = outcome_of(status, getattr(request.state, "error_code", None))
        metrics.observe(route, method, status, duration, reason)

        fields = {
            "request_id": request_id,
            "method": method,
            "route": route,
            "status": status,
            "duration_ms": round(duration * 1000, 2),
            "model_version": service.version,
            "outcome": outcome,
        }
        if reason is not None:
            fields["reject_reason"] = reason
        request_logger.log(LOG_LEVELS[outcome], "request", extra={"fields": fields})

        response.headers["X-Request-ID"] = request_id
        response.headers.update(SECURITY_HEADERS)
        return response

    @app.get("/health")
    async def health(request: Request):
        if not is_ready():
            request.state.error_code = (
                "model_unavailable" if not service.ready else "service_unavailable"
            )
            return JSONResponse(status_code=503, content={"status": "unavailable"})
        return {"status": "healthy", "model_version": service.version}

    @app.post("/predict")
    async def predict_endpoint(request: Request):
        if not service.ready:
            raise ApiError(503, "model_unavailable", "Модель не готова.")
        if not guard.configured:
            raise ApiError(503, "service_unavailable", "Сервис не настроен.")

        # 429 / 401 — до чтения тела запроса
        guard.check(request)

        # 415 / 413 / 400 — до модели
        payload = await read_json_payload(request, settings.max_body_bytes)
        try:
            # Схема ЛР2 проверяется до занятия слота: отклонённый вход
            # не тратит ресурсы модели
            validate_input(payload)
            result = await limiter.run(service.predict, payload)
        except InputValidationError as error:
            status = VALIDATION_STATUS.get(error.code, 422)
            raise ApiError(status, error.code, str(error)) from None
        except PredictionUnavailableError as error:
            raise ApiError(422, "no_known_features", str(error)) from None
        except ModelNotReadyError:
            raise ApiError(503, "model_unavailable", "Модель не готова.") from None

        metrics.predictions.labels(result["prediction"]).inc()
        return {
            **result,
            "model_version": service.version,
            "request_id": request.state.request_id,
        }

    @app.get("/metrics", include_in_schema=False)
    async def metrics_endpoint(request: Request):
        if metrics_token is None:
            raise ApiError(404, "http_404", "Not Found")  # эндпоинт выключен
        require_metrics_token(request, metrics_token)
        metrics.model_ready.set(1 if is_ready() else 0)
        return Response(metrics.render(), media_type=metrics.content_type)

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    # только /static/...: неизвестные пути по-прежнему дают 404 в формате API
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app


app = create_app()
