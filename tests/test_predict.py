import json
from pathlib import Path

import pytest

from src.artifacts import load_model
from src.predict import InputValidationError, predict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE = json.loads(
    (PROJECT_ROOT / "metrics" / "baseline.json").read_text(encoding="utf-8")
)
MODEL_PATH = PROJECT_ROOT / BASELINE["artifact"]["path"]


@pytest.fixture(scope="session")
def pipeline():
    # Модель загружается только при совпадении SHA256 с baseline.json.
    return load_model(MODEL_PATH, expected_sha256=BASELINE["artifact"]["sha256"])


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
    # Будет переписан на этапе 2 ЛР3: сейчас сравнивает код сам с собой.
    text = "Hello world"
    expected_label = int(pipeline.predict([text])[0])

    result = predict({"text": text}, pipeline)

    assert result == {"label": expected_label}
    assert type(result["label"]) is int
