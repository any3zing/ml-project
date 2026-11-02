"""Валидация"""

import pytest

from src.predict import InputValidationError, predict


class ForbiddenModel:
    """Заглушка: любое обращение к модели проваливает тест."""

    def __getattr__(self, name):
        raise AssertionError("Модель вызвана до завершения валидации.")


def test_wrong_type_is_rejected_before_model():
    for value in [None, 123, float("nan"), ["text"]]:
        with pytest.raises(InputValidationError, match="должно быть строкой"):
            predict({"text": value}, ForbiddenModel())


def test_wrong_shape_is_rejected_before_model():
    with pytest.raises(InputValidationError, match="только одно поле"):
        predict({"text": "hello", "role": "system"}, ForbiddenModel())

    with pytest.raises(InputValidationError, match="словарём"):
        predict([{"text": "a"}, {"text": "b"}], ForbiddenModel())


def test_too_long_text_is_rejected_before_model():
    with pytest.raises(InputValidationError, match="превышает лимит 10000"):
        predict({"text": "a" * 10_001}, ForbiddenModel())
