"""ЛР4: аутентификация по токену и rate limiting."""

import time

import pytest

from src.api.security import SlidingWindow

BODY = {"text": "How do I bake chocolate chip cookies?"}


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
    assert "Traceback" not in response.text


@pytest.fixture
def calls(monkeypatch):
    """Счётчик вызовов модели: для отклонённых запросов должен быть 0."""
    made = []

    def install(test_client):
        service = test_client.app.state.model_service
        original = service.predict

        def counted(payload):
            made.append(payload)
            return original(payload)

        monkeypatch.setattr(service, "predict", counted)
        return made

    return install


# --- 401 --------------------------------------------------------------------

def test_missing_and_invalid_token_are_401(make_client, calls):
    with make_client() as client:
        made = calls(client)
        cases = [
            ({"Authorization": ""}, "auth_missing"),
            ({"Authorization": "Bearer wrong-token"}, "auth_invalid"),
            ({"Authorization": "Basic dXNlcjpwYXNz"}, "auth_invalid"),
        ]
        for headers, code in cases:
            response = client.post("/predict", json=BODY, headers=headers)
            assert_error(response, 401, code)
            assert response.headers["WWW-Authenticate"] == "Bearer"
            assert "wrong-token" not in response.text
        assert made == []


def test_valid_token_is_accepted(make_client):
    with make_client() as client:
        assert client.post("/predict", json=BODY).status_code == 200


def test_health_does_not_require_token(make_client):
    with make_client() as client:
        response = client.get("/health", headers={"Authorization": ""})
        assert response.status_code == 200


# --- сервер без токена не готов ----------------------------------------------

@pytest.mark.parametrize(
    ("token", "problem"),
    [(None, "api_token_missing"), ("short", "api_token_too_short")]
)
def test_service_without_server_token_is_not_ready(make_client, token, problem):
    with make_client(api_token=token) as client:
        assert client.get("/health").status_code == 503
        assert_error(client.post("/predict", json=BODY), 503, "service_unavailable")
        assert client.app.state.guard.problem == problem


# --- 429 --------------------------------------------------------------------

def test_rate_limit_per_token(make_client):
    with make_client(rate_limit=3, rate_window=60) as client:
        for _ in range(3):
            assert client.post("/predict", json=BODY).status_code == 200
        response = client.post("/predict", json=BODY)
        assert_error(response, 429, "rate_limited")
        assert int(response.headers["Retry-After"]) >= 1


def test_failed_auth_blocks_address_and_recovers(make_client, calls):
    with make_client(auth_fail_limit=3, auth_fail_window=1.0) as client:
        made = calls(client)
        wrong = {"Authorization": "Bearer wrong-token"}
        for _ in range(3):
            assert_error(client.post("/predict", json=BODY, headers=wrong),
                         401, "auth_invalid")

        # адрес заблокирован: и для неверного, и для верного токена
        assert_error(client.post("/predict", json=BODY, headers=wrong),
                     429, "auth_blocked")
        assert_error(client.post("/predict", json=BODY), 429, "auth_blocked")
        assert made == []

        time.sleep(1.1)  # окно закончилось — восстановление
        assert client.post("/predict", json=BODY).status_code == 200


def test_forwarded_header_does_not_change_client_key(make_client):
    # приложение не читает X-Forwarded-For: смена «адреса» не снимает блок
    with make_client(auth_fail_limit=2, auth_fail_window=60) as client:
        for i in range(2):
            client.post("/predict", json=BODY, headers={
                "Authorization": "Bearer wrong", "X-Forwarded-For": f"10.0.0.{i}"})
        response = client.post("/predict", json=BODY, headers={
            "Authorization": "Bearer wrong", "X-Forwarded-For": "10.0.0.99"})
        assert_error(response, 429, "auth_blocked")


# --- скользящее окно ---------------------------------------------------------

def test_sliding_window_with_fake_clock():
    now = [100.0]
    window = SlidingWindow(limit=2, window=10, clock=lambda: now[0])
    assert window.allow("k") and window.allow("k")
    assert not window.allow("k")
    assert window.retry_after("k") == 10
    now[0] += 10.1
    assert window.allow("k")
