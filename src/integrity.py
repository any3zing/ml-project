"""Подсчёт и проверка SHA256 файлов."""

import hashlib
import hmac
from pathlib import Path

CHUNK_SIZE = 1024 * 1024


class IntegrityError(RuntimeError):
    """Хэш файла не совпадает с ожидаемым."""


def sha256_file(path):
    """Возвращает SHA256 файла в шестнадцатеричном виде."""
    hasher = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(CHUNK_SIZE), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_sha256(path, expected_sha256):
    """Проверяет хэш файла; при несовпадении вызывает IntegrityError."""
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise IntegrityError("Ожидаемый SHA256 не задан или имеет неверный формат.")

    actual = sha256_file(path)
    if not hmac.compare_digest(actual, expected_sha256.lower()):
        raise IntegrityError(
            f"SHA256 файла {path} не совпадает: "
            f"ожидался {expected_sha256}, получен {actual}."
        )
    return actual
