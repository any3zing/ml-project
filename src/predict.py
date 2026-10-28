"""Предсказание класса текста с предварительной валидацией."""

MAX_TEXT_LENGTH = 10_000


class InputValidationError(ValueError):
    """Контролируемая ошибка входных данных."""

class PredictionUnavailableError(ValueError):
    """Недостаточно признаков для классификации текста."""


def validate_input(payload, *, max_text_length=MAX_TEXT_LENGTH):
    """Проверяет структуру и возвращает исходный текст."""
    if not isinstance(payload, dict):
        raise InputValidationError(
            "Вход должен быть словарём с единственным полем 'text'."
        )

    if "text" not in payload:
        raise InputValidationError("Отсутствует обязательное поле 'text'.")

    if len(payload) != 1:
        raise InputValidationError(
            "Разрешено только одно поле: 'text'."
        )

    text = payload["text"]

    if not isinstance(text, str):
        raise InputValidationError(
            "Поле 'text' должно быть строкой; "
            "None, числа, NaN, Inf и списки не допускаются."
        )

    if len(text) > max_text_length:
        raise InputValidationError(
            f"Длина текста превышает лимит {max_text_length} символов."
        )

    if not text.strip():
        raise InputValidationError(
            "Поле 'text' не должно быть пустым или пробельным."
        )

    return text


def predict(payload, pipeline, *, max_text_length=MAX_TEXT_LENGTH):
    """Проверяет вход, преобразует текст и возвращает класс."""
    text = validate_input(
        payload,
        max_text_length=max_text_length,
    )

    features = pipeline.named_steps["tfidf"].transform([text])

    if features.nnz == 0:
        raise PredictionUnavailableError(
            "Классификация невозможна: текст не содержит "
            "признаков из словаря модели."
        )

    prediction = pipeline.named_steps["classifier"].predict(features)

    return {"label": int(prediction[0])}
