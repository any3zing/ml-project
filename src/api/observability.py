"""Структурированные JSON-логи и метрики Prometheus.

Логи: одна JSON-строка на событие в stdout. В лог запроса попадают только
служебные поля: время, request_id, маршрут, метод, код, длительность,
версия модели, исход и причина отказа. Текст запроса, токены, IP-адреса,
User-Agent и query string не пишутся.

Метрики: отдельный CollectorRegistry на приложение (тесты создают много
приложений). Значения labels берутся только из фиксированных множеств:
иначе число временных рядов зависело бы от клиента.
"""

import json
import logging
import sys
from datetime import UTC, datetime

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

KNOWN_ROUTES = ("/", "/health", "/predict", "/metrics")
KNOWN_METHODS = ("GET", "HEAD", "POST", "OPTIONS")
PREDICTIONS = ("benign", "malicious")
REJECTION_REASONS = (
    # аутентификация и частота
    "auth_missing", "auth_invalid", "auth_blocked", "rate_limited",
    "metrics_unauthorized",
    # размер и формат тела
    "body_too_large", "invalid_content_length", "unsupported_media_type",
    "invalid_json",
    # схема ЛР2
    "invalid_shape", "missing_field", "unexpected_field", "invalid_type",
    "text_too_long", "empty_text", "no_known_features", "invalid_input",
    # ресурсы и готовность
    "busy", "timeout", "model_unavailable", "service_unavailable",
    # маршрутизатор
    "http_404", "http_405",
    "other",
)
DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)


# --- логи ---------------------------------------------------------------------

class JsonFormatter(logging.Formatter):
    """Запись лога -> одна JSON-строка. Доп. поля — в extra={"fields": {...}}."""

    def format(self, record):
        entry = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        entry.update(getattr(record, "fields", {}))
        if record.exc_info and record.exc_info[0] is not None:
            # только тип исключения: в тексте ошибки могут оказаться данные входа
            entry["exc_type"] = record.exc_info[0].__name__
        return json.dumps(entry, ensure_ascii=False, default=str)


def setup_logging(level=logging.INFO):
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # служебные сообщения uvicorn — тоже JSON, через корневой логгер
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
    # access-лог uvicorn пишет IP и строку запроса — отключён
    logging.getLogger("uvicorn.access").disabled = True


# --- нормализация labels --------------------------------------------------------

def route_label(path):
    if path in KNOWN_ROUTES:
        return path
    if path.startswith("/static/"):
        return "/static"
    return "other"


def method_label(method):
    return method if method in KNOWN_METHODS else "other"


def outcome_of(status, code):
    """(исход, причина отказа) по HTTP-коду и машинному коду ошибки."""
    if status < 400:
        return "ok", None
    if code is None or code == "internal_error":
        return "error", None
    return "rejected", code if code in REJECTION_REASONS else "other"


# --- метрики -------------------------------------------------------------------

class Metrics:
    content_type = CONTENT_TYPE_LATEST

    def __init__(self, model_version):
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "api_requests", "HTTP requests",
            ("route", "method", "status_class"), registry=self.registry,
        )
        self.duration = Histogram(
            "api_request_duration_seconds", "Request duration",
            ("route",), buckets=DURATION_BUCKETS, registry=self.registry,
        )
        self.rejections = Counter(
            "api_rejections", "Rejected requests by reason",
            ("reason",), registry=self.registry,
        )
        self.predictions = Counter(
            "api_predictions", "Predictions by class",
            ("prediction",), registry=self.registry,
        )
        self.model_ready = Gauge(
            "model_ready", "1 if model is loaded and service is configured",
            registry=self.registry,
        )
        self.model_info = Gauge(
            "model_info", "Deployed model version",
            ("version",), registry=self.registry,
        )
        self.model_info.labels(model_version).set(1)
        # нулевые ряды сразу: снимок «до» уже содержит все причины
        for reason in REJECTION_REASONS:
            self.rejections.labels(reason)
        for prediction in PREDICTIONS:
            self.predictions.labels(prediction)

    def observe(self, route, method, status, duration, reason):
        self.requests.labels(route, method, f"{status // 100}xx").inc()
        self.duration.labels(route).observe(duration)
        if reason is not None:
            self.rejections.labels(reason).inc()

    def render(self):
        return generate_latest(self.registry)
