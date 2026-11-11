# ЛР4: образ API классификатора (FastAPI + uvicorn)
FROM python:3.14.4-slim@sha256:2ca02f32b4d9d893863367ce07ec1972819f476dd38d8612f2a9cb6a41cbb727

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
# CVE-2026-13221, CVE-2026-42496, CVE-2026-8376 (CRITICAL, найдены Trivy):
# в базовом образе perl-base 5.40.1-6, исправление — 5.40.1-6+deb13u1.
# Обновляем только этот пакет; убрать нельзя (Essential в Debian).
RUN apt-get update \
 && apt-get install -y --no-install-recommends --only-upgrade perl-base \
 && rm -rf /var/lib/apt/lists/*

# Только runtime-зависимости. Список полный и закреплённый:
# --no-deps не даёт pip подтянуть незафиксированные пакеты
COPY requirements-runtime.txt .
RUN pip install --no-cache-dir --no-deps -r requirements-runtime.txt \
 && pip check

# Непривилегированный пользователь
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home \
    --shell /usr/sbin/nologin app

# Только код сервиса, страница, эталон SHA256 и модель ЛР2.
# Файлы принадлежат root: пользователь app может их читать, но не менять.
COPY src/__init__.py src/paths.py src/integrity.py src/artifacts.py \
     src/predict.py src/smoke.py src/
COPY src/api/ src/api/
COPY static/ static/
COPY metrics/baseline.json metrics/
COPY models/baseline.joblib models/

USER 10001:10001
EXPOSE 8000

# Docker сам опрашивает /health: 503 или нет ответа -> unhealthy
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --start-interval=2s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

# 0.0.0.0 — интерфейс внутри контейнера; на хосте порт публикуется только на 127.0.0.1.
# Секреты (API_TOKEN, METRICS_TOKEN) передаются при запуске, в образе их нет.
ENTRYPOINT ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000", \
            "--workers", "1", "--no-proxy-headers", "--no-access-log", \
            "--limit-concurrency", "32", "--timeout-keep-alive", "5"]
