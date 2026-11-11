"""Предсказание класса текста с предварительной валидацией."""

MAX_TEXT_LENGTH = 10_000


class InputValidationError(ValueError):
    """Контролируемая ошибка входных данных; code — машинный код причины."""

    def __init__(self, message, code="invalid_input"):
        super().__init__(message)
        self.code = code


class PredictionUnavailableError(ValueError):
    """Недостаточно признаков для классификации текста."""


def validate_input(payload, *, max_text_length=MAX_TEXT_LENGTH):
    """Проверяет структуру и возвращает исходный текст."""
    if not isinstance(payload, dict):
        raise InputValidationError(
            "Вход должен быть словарём с единственным полем 'text'.",
            code="invalid_shape",
        )

    if "text" not in payload:
        raise InputValidationError(
            "Отсутствует обязательное поле 'text'.",
            code="missing_field",
        )

    if len(payload) != 1:
        raise InputValidationError(
            "Разрешено только одно поле: 'text'.",
            code="unexpected_field",
        )

    text = payload["text"]

    if not isinstance(text, str):
        raise InputValidationError(
            "Поле 'text' должно быть строкой; "
            "None, числа, NaN, Inf и списки не допускаются.",
            code="invalid_type",
        )

    if len(text) > max_text_length:
        raise InputValidationError(
            f"Длина текста превышает лимит {max_text_length} символов.",
            code="text_too_long",
        )

    if not text.strip():
        raise InputValidationError(
            "Поле 'text' не должно быть пустым или пробельным.",
            code="empty_text",
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

