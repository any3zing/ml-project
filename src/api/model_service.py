"""Загрузка модели с проверкой целостности и состояние готовности сервиса.

Порядок при старте:
  1. эталонный SHA256 читается из отдельного файла (metrics/baseline.json);
  2. load_model сверяет SHA256 файла модели и только потом вызывает joblib.load;
  3. проверяется, что загружен Pipeline с шагами tfidf и classifier;
  4. контрольные предсказания (те же примеры, что в src.smoke).
Любая ошибка -> сервис не готов (ready = False), причина пишется в лог.
"""

import json
import logging
from pathlib import Path

from sklearn.pipeline import Pipeline

from src.artifacts import load_model
from src.integrity import IntegrityError
from src.predict import predict
from src.smoke import CHECKS

logger = logging.getLogger("api.model")

LABEL_NAMES = {0: "benign", 1: "malicious"}
REQUIRED_STEPS = ("tfidf", "classifier")


class ModelNotReadyError(RuntimeError):
    """Модель не загружена: предсказание невозможно."""


def read_reference_sha256(path):
    """Возвращает эталонный SHA256 модели из baseline.json."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    digest = data["artifact"]["sha256"]
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("Эталонный SHA256 имеет неверный формат.")
    return digest


class ModelService:
    """Хранит загруженную модель; до успешной загрузки сервис не готов."""

    def __init__(self, settings):
        self._settings = settings
        self._pipeline = None
        self.failure = None  # код причины неготовности (для логов и тестов)

    @property
    def ready(self):
        return self._pipeline is not None

    @property
    def version(self):
        return self._settings.model_version

    def load(self):
        """Загружает модель; возвращает True, если сервис готов."""
        self._pipeline = None

        try:
            expected = read_reference_sha256(self._settings.reference_path)
        except (OSError, ValueError, KeyError, TypeError) as error:
            return self._fail("reference_unavailable", error)

        try:
            pipeline = load_model(self._settings.model_path, expected_sha256=expected)
        except IntegrityError as error:
            return self._fail("model_integrity_failed", error)
        except OSError as error:
            return self._fail("model_unavailable", error)
        except Exception as error:  # любая ошибка распаковки -> не готов
            return self._fail("model_load_failed", error)

        if not isinstance(pipeline, Pipeline) or any(
            step not in pipeline.named_steps for step in REQUIRED_STEPS
        ):
            return self._fail("model_invalid", None)

        try:
            for text, expected_label in CHECKS:
                if predict({"text": text}, pipeline)["label"] != expected_label:
                    return self._fail("model_selfcheck_failed", None)
        except Exception as error:
            return self._fail("model_selfcheck_failed", error)

        self._pipeline = pipeline
        self.failure = None
        logger.info(
            "model_loaded",
            extra={"fields": {
                "model_version": self.version, "sha256_prefix": expected[:12],
            }},
        )
        return True

    def _fail(self, reason, error):
        self._pipeline = None
        self.failure = reason
        detail = type(error).__name__ if error is not None else "-"
        logger.error(
            "model_not_ready", extra={"fields": {"reason": reason, "error": detail}}
        )
        return False

    def predict(self, payload):
        """Валидация и предсказание функцией ЛР2 (src.predict.predict)."""
        if self._pipeline is None:
            raise ModelNotReadyError("Модель не загружена.")
        label = predict(payload, self._pipeline)["label"]
        return {"prediction": LABEL_NAMES[label], "label": label}
