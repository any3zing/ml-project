"""Настройки сервиса.

Значения по умолчанию подходят для запуска из корня репозитория и в Docker;
переопределяются переменными окружения (см. from_env).
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from src.paths import METRICS_DIR, MODELS_DIR, resolve

# Модель ЛР2 из GitHub Release lab2
MODEL_VERSION = "lab2-v1"
DEFAULT_MODEL_PATH = MODELS_DIR / "baseline.joblib"
# Эталонный SHA256 хранится отдельно от модели: в metrics/baseline.json (в git)
DEFAULT_REFERENCE_PATH = METRICS_DIR / "baseline.json"


def _positive(env, name, default, cast):
    """Читает положительное число из окружения; ошибка — сервис не стартует."""
    raw = env.get(name)
    if raw is None:
        return default
    value = cast(raw)
    if value <= 0:
        raise ValueError(f"{name} должно быть больше 0.")
    return value


def read_secret(env, name):
    """Секрет из файла <NAME>_FILE (приоритет) или переменной <NAME>."""
    path = env.get(f"{name}_FILE")
    if path:
        value = Path(path).read_text(encoding="utf-8").strip()
    else:
        value = env.get(name, "").strip()
    return value or None


@dataclass(frozen=True)
class Settings:
    model_path: Path = DEFAULT_MODEL_PATH
    reference_path: Path = DEFAULT_REFERENCE_PATH
    model_version: str = MODEL_VERSION
    enable_docs: bool = False  # /docs и /openapi.json выключены по умолчанию

    # Ограничения ресурсов (обоснование — в README)
    max_body_bytes: int = 65_536      # 10 000 симв. x до 4 байт UTF-8 + JSON
    max_concurrent: int = 4           # одновременных предсказаний
    queue_timeout: float = 0.5        # ожидание свободного слота, с
    inference_timeout: float = 2.0    # время ответа на предсказание, с

    # Аутентификация и частота запросов
    api_token: str | None = field(default=None, repr=False)  # не в логи
    rate_limit: int = 30              # запросов на токен
    rate_window: float = 60.0         # за столько секунд
    auth_fail_limit: int = 10         # неудачных попыток с адреса
    auth_fail_window: float = 60.0    # за столько секунд -> блокировка
    metrics_token: str | None = field(default=None, repr=False)  # для /metrics

    @classmethod
    def from_env(cls):
        env = os.environ
        return cls(
            model_path=resolve(env.get("MODEL_PATH", DEFAULT_MODEL_PATH)),
            reference_path=resolve(
                env.get("MODEL_REFERENCE_PATH", DEFAULT_REFERENCE_PATH)
            ),
            enable_docs=env.get("ENABLE_DOCS", "0") == "1",
            max_body_bytes=_positive(env, "MAX_BODY_BYTES", cls.max_body_bytes, int),
            max_concurrent=_positive(env, "MAX_CONCURRENT", cls.max_concurrent, int),
            queue_timeout=_positive(env, "QUEUE_TIMEOUT", cls.queue_timeout, float),
            inference_timeout=_positive(
                env, "INFERENCE_TIMEOUT", cls.inference_timeout, float
            ),
            api_token=read_secret(env, "API_TOKEN"),
            metrics_token=read_secret(env, "METRICS_TOKEN"),
            rate_limit=_positive(env, "RATE_LIMIT", cls.rate_limit, int),
            rate_window=_positive(env, "RATE_WINDOW", cls.rate_window, float),
            auth_fail_limit=_positive(
                env, "AUTH_FAIL_LIMIT", cls.auth_fail_limit, int
            ),
            auth_fail_window=_positive(
                env, "AUTH_FAIL_WINDOW", cls.auth_fail_window, float
            ),
        )
