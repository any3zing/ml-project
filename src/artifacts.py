"""Сохранение и загрузка доверенной модели."""

from pathlib import Path

import joblib


def save_model(pipeline, path):
    """Сохраняет обученный Pipeline."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, path)


def load_model(path, *, trusted=False):
    """Загружает только явно отмеченный доверенный артефакт.

    trusted=True не проверяет содержимое файла.
    Нельзя загружать непроверенные сторонние модели.
    """
    if not trusted:
        raise ValueError(
            "Загрузка запрещена без подтверждения доверия к файлу."
        )

    return joblib.load(Path(path))