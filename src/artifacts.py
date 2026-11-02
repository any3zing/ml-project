"""Сохранение и загрузка собственной модели с проверкой SHA256.

joblib основан на pickle: загрузка файла может выполнить код.
Поэтому модель загружается только при совпадении SHA256 с хэшем,
полученным из доверенного источника (отчёт обучения, baseline.json).
"""

from pathlib import Path

import joblib

from src.integrity import sha256_file, verify_sha256


def save_model(pipeline, path):
    """Сохраняет Pipeline и файл <model>.sha256; возвращает SHA256."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, path)

    digest = sha256_file(path)
    path.with_name(path.name + ".sha256").write_text(
        f"{digest}  {path.name}\n", encoding="utf-8"
    )
    return digest


def load_model(path, *, expected_sha256):
    """Загружает модель только после проверки SHA256."""
    verify_sha256(path, expected_sha256)
    return joblib.load(Path(path))
