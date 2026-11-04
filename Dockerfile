# Образ для smoke-проверки модели
FROM python:3.14.4-slim@sha256:2ca02f32b4d9d893863367ce07ec1972819f476dd38d8612f2a9cb6a41cbb727

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Только runtime-зависимости
COPY requirements-runtime.txt .
RUN pip install --no-cache-dir -r requirements-runtime.txt

# Непривилегированный пользователь
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home \
    --shell /usr/sbin/nologin app

# Только модули, нужные для предсказания, и явно выбранная модель.
# Файлы принадлежат root: пользователь app может их читать, но не менять.
COPY src/__init__.py src/paths.py src/integrity.py src/artifacts.py \
     src/predict.py src/smoke.py src/
COPY models/candidate.joblib models/candidate.joblib.sha256 models/

USER 10001:10001

# Контейнер одноразовый (smoke), постоянного сервиса нет
HEALTHCHECK NONE

ENTRYPOINT ["python", "-m", "src.smoke"]
