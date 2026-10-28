from unittest.mock import Mock

import pytest

from src.predict import InputValidationError, predict


@pytest.mark.parametrize(
    "payload, expected_message",
    [
        pytest.param(
            "обычная строка",
            "Вход должен быть словарём",
            id="wrong_input_type",
        ),
        pytest.param(
            {},
            "Отсутствует обязательное поле",
            id="missing_text",
        ),
        pytest.param(
            {"text": "hello", "extra": 123},
            "Разрешено только одно поле",
            id="extra_field",
        ),
        pytest.param(
            {"text": 123},
            "должно быть строкой",
            id="numeric_text",
        ),
        pytest.param(
            {"text": ["hello"]},
            "должно быть строкой",
            id="nested_list",
        ),
        pytest.param(
            {"text": ""},
            "не должно быть пустым",
            id="empty_text",
        ),
        pytest.param(
            {"text": " \n\t "},
            "не должно быть пустым",
            id="whitespace_text",
        ),
        pytest.param(
            {"text": None},
            "должно быть строкой",
            id="none_text",
        ),
        pytest.param(
            {"text": float("nan")},
            "должно быть строкой",
            id="nan_text",
        ),
        pytest.param(
            {"text": float("inf")},
            "должно быть строкой",
            id="inf_text",
        ),
    ],
)
def test_invalid_input_is_rejected(payload, expected_message):
    pipeline = Mock()

    with pytest.raises(InputValidationError, match=expected_message):
        predict(payload, pipeline)

    pipeline.predict.assert_not_called()


def test_text_above_limit_is_rejected():
    pipeline = Mock()

    with pytest.raises(InputValidationError, match="превышает лимит 10"):
        predict(
            {"text": "a" * 11},
            pipeline,
            max_text_length=10,
        )

    pipeline.predict.assert_not_called()


def test_valid_input_returns_prediction():
    pipeline = Mock()
    pipeline.predict.return_value = [1]

    result = predict({"text": "Hello world"}, pipeline)

    assert result == {"label": 1}
    pipeline.predict.assert_called_once_with(["Hello world"])


def test_text_at_limit_is_accepted():
    pipeline = Mock()
    pipeline.predict.return_value = [0]
    text = "a" * 10

    result = predict(
        {"text": text},
        pipeline,
        max_text_length=10,
    )

    assert result == {"label": 0}
    pipeline.predict.assert_called_once_with([text])
