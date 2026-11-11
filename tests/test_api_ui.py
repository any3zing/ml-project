"""ЛР4, этап 5: веб-интерфейс, заголовки безопасности, отсутствие CORS."""
import re

import pytest

from src.paths import PROJECT_ROOT

STATIC = PROJECT_ROOT / "static"


@pytest.fixture(scope="module")
def client(make_client):
    with make_client() as test_client:
        yield test_client


def test_index_page_is_served(client, api_token):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'id="predict-form"' in response.text
    assert api_token not in response.text  # токен не встроен в страницу


def test_static_assets(client):
    for path, kind in [
        ("/static/app.js", "javascript"),
        ("/static/style.css", "text/css"),
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert kind in response.headers["content-type"]


def test_security_headers_on_page_and_api(client):
    for response in (
        client.get("/"),
        client.post("/predict", json={"text": "hello world"}),
    ):
        headers = response.headers
        csp = headers["content-security-policy"]
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["referrer-policy"] == "no-referrer"
        assert headers["cache-control"] == "no-store"


def test_cors_is_not_enabled(client):
    origin = {"Origin": "https://evil.example"}
    response = client.get("/health", headers=origin)
    assert "access-control-allow-origin" not in response.headers

    preflight = client.options(
        "/predict", headers={**origin, "Access-Control-Request-Method": "POST"}
    )
    assert preflight.status_code == 405
    assert "access-control-allow-origin" not in preflight.headers


def test_static_does_not_expose_project_files(client):
    for path in [
        "/static/",
        "/static/../metrics/baseline.json",
        "/static/%2e%2e/src/api/settings.py",
        "/static/%2e%2e/models/baseline.joblib",
    ]:
        assert client.get(path).status_code == 404


def test_frontend_source_rules():
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    for forbidden in (
        "localStorage", "sessionStorage", "document.cookie",
        "innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(",
    ):
        assert forbidden not in script

    page = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "<script>" not in page  # нет inline-скриптов (их запрещает CSP)
    assert 'type="password"' in page
    # у полей формы нет name: даже без JS браузер не отправит токен в URL
    fields = re.findall(r"<(?:input|textarea|select)\b[^>]*>", page)
    assert fields  # поля действительно найдены
    assert all(" name=" not in field for field in fields)
