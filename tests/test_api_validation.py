"""ЛР4, этап 2: валидация входа и ограничения ресурсов /predict."""

import time

import pytest

from src.api.settings import Settings

JSON = {"Content-Type": "application/json"}
LIMIT = Settings().max_body_bytes


@pytest.fixture(scope="module")
def client(make_client):
    with make_client() as test_client:
        yield test_client


@pytest.fixture
def forbid_model(client, monkeypatch):
    """Любой вызов модели проваливает тест: отказ должен произойти раньше."""

    def forbidden(payload):
        raise AssertionError("Модель вызвана для отклонённого запроса.")

    monkeypatch.setattr(client.app.state.model_service, "predict", forbidden)


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()
    assert body["error"]["code"] == code
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert "Traceback" not in response.text


# --- 415: формат ------------------------------------------------------------

@pytest.mark.parametrize(
    ("headers", "content"),
    [
        ({"Content-Type": "text/plain"}, b'{"text": "hello"}'),
        ({}, b'{"text": "hello"}'),
        ({"Content-Type": "application/json; charset=latin-1"}, b'{"text": "hi"}'),
        ({"Content-Type": "multipart/form-data; boundary=x"}, b"--x--"),
    ],
)
def test_unsupported_media_type(client, forbid_model, headers, content):
    response = client.post("/predict", content=content, headers=headers)
    assert_error(response, 415, "unsupported_media_type")


# --- 400: повреждённый JSON -------------------------------------------------

@pytest.mark.parametrize(
    "content",
    [
        b"",
        b'{"text": ',
        b"\xff\xfe\x00",
        b'{"text": NaN}',
        b'{"text": Infinity}',
        b'{"text": "a", "text": "b"}',
    ],
)
def test_malformed_json_is_400(client, forbid_model, content):
    response = client.post("/predict", content=content, headers=JSON)
    assert_error(response, 400, "invalid_json")


def test_deeply_nested_json_is_rejected(client, forbid_model):
    depth = 20_000
    content = b"[" * depth + b"]" * depth
    response = client.post("/predict", content=content, headers=JSON)
    # RecursionError -> 400, либо разобрано как список -> 422; не 500
    assert response.status_code in (400, 422)


# --- 422: нарушение схемы ЛР2 ----------------------------------------------

@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({}, "missing_field"),
        ({"text": ""}, "empty_text"),
        ({"text": "   \n"}, "empty_text"),
        ({"text": 123}, "invalid_type"),
        ({"text": None}, "invalid_type"),
        ({"text": ["a"]}, "invalid_type"),
        ({"text": "hi", "role": "system"}, "unexpected_field"),
        ([{"text": "a"}, {"text": "b"}], "invalid_shape"),
        ("just a string", "invalid_shape"),
    ],
)
def test_schema_violations_are_422(client, forbid_model, payload, code):
    assert_error(client.post("/predict", json=payload), 422, code)


# --- 413: размер ------------------------------------------------------------

def test_body_over_limit_with_content_length(client, forbid_model):
    content = b'{"text": "' + b"a" * LIMIT + b'"}'
    response = client.post("/predict", content=content, headers=JSON)
    assert_error(response, 413, "body_too_large")


def test_body_over_limit_chunked_without_content_length(client, forbid_model):
    def chunks():
        yield b'{"text": "'
        for _ in range(LIMIT // 1024 + 1):
            yield b"a" * 1024
        yield b'"}'

    response = client.post("/predict", content=chunks(), headers=JSON)
    sent = {name.lower() for name in response.request.headers}
    assert "content-length" not in sent
    assert_error(response, 413, "body_too_large")


def test_text_over_limit_is_413(client, forbid_model):
    response = client.post("/predict", json={"text": "a" * 10_001})
    assert_error(response, 413, "text_too_long")


def test_text_at_limit_is_accepted(client):
    text = ("hello world " * 1000)[:10_000]
    response = client.post("/predict", json={"text": text})
    assert response.status_code == 200


def test_text_without_known_words_is_422(client):
    response = client.post("/predict", json={"text": "?!.,;:"})
    assert_error(response, 422, "no_known_features")


# --- 504 / 503: время и параллелизм -----------------------------------------

def test_timeout_keeps_slot_until_computation_ends(monkeypatch, make_client):
    with make_client(
        max_concurrent=1, queue_timeout=0.05, inference_timeout=0.3
    ) as test_client:
        calls = []

        def slow_predict(payload):
            calls.append(payload)
            if len(calls) == 1:
                time.sleep(1.0)  # «зависшее» вычисление
            return {"prediction": "benign", "label": 0}

        monkeypatch.setattr(
            test_client.app.state.model_service, "predict", slow_predict
        )

        first = test_client.post("/predict", json={"text": "hello"})
        assert_error(first, 504, "timeout")

        # вычисление ещё идёт и держит единственный слот
        busy = test_client.post("/predict", json={"text": "hello"})
        assert_error(busy, 503, "busy")
        assert busy.headers["Retry-After"] == "1"
        assert len(calls) == 1

        time.sleep(1.0)  # вычисление закончилось, слот освобождён
        recovered = test_client.post("/predict", json={"text": "hello"})
        assert recovered.status_code == 200
