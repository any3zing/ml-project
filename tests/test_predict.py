from pathlib import Path

import joblib
import pytest

from src.predict import InputValidationError, predict


MODEL_PATH = (
    Path(__file__).resolve().parents[1]
    / "models"
    / "baseline.joblib"
)


@pytest.fixture(scope="session")
def pipeline():
    return joblib.load(MODEL_PATH)


def test_wrong_input_type_is_rejected():
    with pytest.raises(
        InputValidationError,
        match="Вход должен быть словарём",
    ):
        predict("обычная строка", pipeline=None)


def test_missing_text_is_rejected():
    with pytest.raises(
        InputValidationError,
        match="Отсутствует обязательное поле",
    ):
        predict({}, pipeline=None)


def test_whitespace_text_is_rejected():
    with pytest.raises(
        InputValidationError,
        match="не должно быть пустым",
    ):
        predict({"text": " \n\t "}, pipeline=None)


def test_text_above_limit_is_rejected():
    with pytest.raises(
        InputValidationError,
        match="превышает лимит 10",
    ):
        predict(
            {"text": "a" * 11},
            pipeline=None,
            max_text_length=10,
        )


def test_valid_input_returns_prediction(pipeline):
    text = "Hello world"
    expected_label = int(pipeline.predict([text])[0])

    result = predict({"text": text}, pipeline)

    assert result == {"label": expected_label}
    assert type(result["label"]) is int