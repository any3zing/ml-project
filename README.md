# ML Project

Учебный проект по дисциплине «Киберустойчивость систем ИИ».
Задача: бинарная классификация текста — `0` benign, `1` malicious (prompt injection).

- ЛР2 — модель (TF-IDF + линейный классификатор), baseline `metrics/baseline.json`.
- ЛР3 — CI/CD: quality gates для данных и модели, проверки кода, зависимостей и образа.
- ЛР4 — защищённый HTTP API модели, веб-страница, логи, метрики и сценарий обнаружения.

## Структура проекта

- `configs/` — источник данных (ревизия, SHA256), правила data gate и model gate
- `src/` — код получения модели:
  - `data.py` — скачивание, проверка SHA256, разбиение train/test
  - `preprocess.py` — TF-IDF с параметрами, выбранными в ЛР2
  - `train.py` — сборка и обучение Pipeline
  - `metrics.py` — метрики качества
  - `evaluate.py` — обучение и оценка одной командой
  - `artifacts.py`, `integrity.py` — сохранение и загрузка модели с проверкой SHA256
  - `predict.py` — валидация входа и предсказание (схема ЛР2, общая для оценки и API)
  - `data_gate.py`, `model_gate.py` — quality gates ЛР3
- `src/api/` — сервис ЛР4:
  - `app.py` — приложение FastAPI, маршруты, middleware логов и метрик
  - `model_service.py` — загрузка модели при старте с проверкой SHA256 и самопроверкой
  - `validation.py` — Content-Type, потоковое ограничение тела, строгий JSON
  - `limits.py` — ограничение параллелизма и времени предсказания
  - `security.py` — API-токен, rate limiting, токен `/metrics`
  - `errors.py` — единый формат ошибок
  - `observability.py` — JSON-логи и метрики Prometheus
  - `settings.py` — настройки из переменных окружения
- `static/` — веб-страница (`index.html`, `app.js`, `style.css`)
- `scripts/api_checks.sh` — проверки API через curl против запущенного сервиса
- `scripts/detection_scenario.py` — сценарий обнаружения подбора токена
- `metrics/baseline.json` — baseline ЛР2 и эталонный SHA256 модели (не перезаписывается)
- `notebooks/` — исследование и подбор гиперпараметров
- `tests/` — автоматические тесты (модель, данные, API)
- `data/`, `models/`, `reports/` — не хранятся в Git, создаются командами ниже

## Установка

```bash
git clone https://github.com/any3zing/ml-project.git
cd ml-project
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Данные

Датасет: [neuralchemy/Prompt-injection-dataset](https://huggingface.co/datasets/neuralchemy/Prompt-injection-dataset),
лицензия Apache-2.0, конфигурация `core`, ревизия `7d70432d…`.
Части train, validation, test склеиваются в этом порядке в `data/dataset.csv` (6 274 строки).

```bash
python -m src.data fetch    # скачать, проверить SHA256 частей и итогового CSV
python -m src.data verify   # проверить уже скачанный файл
```

Ожидаемый SHA256 `data/dataset.csv`:
`33f686bc2167c5d0c86c8033541d70792d5f46cf83aaf32b653c2c8681e2af97`.
При несовпадении команда завершается с кодом 1.

## Обучение и оценка

```bash
python -m src.evaluate
```

Команда проверяет данные, выполняет разбиение 80/20 (`seed=42`, стратификация по `source` и `label`),
обучает модель, оценивает её на отложенной выборке (1 255 строк) и сохраняет:

- `models/candidate.joblib` и `models/candidate.joblib.sha256`;
- `reports/candidate_metrics.json` — метрики, SHA256 модели и данных, параметры, версии.

Ожидаемый результат: F1-macro 0.9499, accuracy 0.9522 (совпадает с baseline ЛР2).

Подбор гиперпараметров (GridSearchCV) выполнен в `notebooks/Lab2.ipynb`;
выбранные параметры зафиксированы в `src/preprocess.py` и `src/train.py`.

## Предсказание из Python

```bash
python - <<'PY'
from src.artifacts import load_model
from src.predict import predict

sha = open("models/candidate.joblib.sha256").read().split()[0]
pipeline = load_model("models/candidate.joblib", expected_sha256=sha)
print(predict({"text": "What is machine learning?"}, pipeline))
PY
```

joblib основан на pickle, поэтому модель загружается только при совпадении SHA256
с хэшем из доверенного источника. Сторонние файлы моделей загружать нельзя.

## API модели (ЛР4)

### Модель и запуск

Сервис использует модель ЛР2 из GitHub Release `lab2`, версия `lab2-v1`.
Эталонный SHA256 хранится отдельно от модели — в `metrics/baseline.json` (`artifact.sha256`, в Git):
`5f4ba90c7ef2f3a1e5e9c22ccabc178aa52096707a1d83542d359802aacfd869`.

```bash
mkdir -p models
curl -fsSL -o models/baseline.joblib \
  https://github.com/any3zing/ml-project/releases/download/lab2/baseline.joblib
echo "5f4ba90c7ef2f3a1e5e9c22ccabc178aa52096707a1d83542d359802aacfd869  models/baseline.joblib" | sha256sum --check
```

Токены создаются один раз и хранятся вне репозитория, с правами `600`:

```bash
mkdir -p ~/.config/ml-project && chmod 700 ~/.config/ml-project
umask 077
python -c "import secrets; print(secrets.token_urlsafe(32))" > ~/.config/ml-project/api_token
python -c "import secrets; print(secrets.token_urlsafe(32))" > ~/.config/ml-project/metrics_token
```

Локальный запуск (только loopback):

```bash
API_TOKEN_FILE=~/.config/ml-project/api_token \
METRICS_TOKEN_FILE=~/.config/ml-project/metrics_token \
  uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

Страница: `http://127.0.0.1:8000/`. Документация OpenAPI (`/docs`) по умолчанию выключена
(`ENABLE_DOCS=1` — включить).

Порядок старта (`model_service.py`): эталонный SHA256 читается из `baseline.json` →
`load_model` сверяет SHA256 файла и только потом вызывает `joblib.load` → проверяется, что
загружен `Pipeline` с шагами `tfidf` и `classifier` → два контрольных предсказания (те же, что в `src.smoke`).
Модель загружается один раз при старте, а не на каждый запрос. При любой ошибке сервис
запускается, но не готов: `/health` и `/predict` отвечают 503, в лог пишется причина
(`model_integrity_failed`, `model_unavailable`, `model_load_failed`, `model_invalid`,
`model_selfcheck_failed`, `reference_unavailable`). Без серверного токена (или если он короче
32 символов) сервис тоже не готов: `api_token_missing` / `api_token_too_short`.

Пользователь не может загрузить модель или файл: API принимает только JSON с текстом,
путь к модели задаётся администратором при запуске.

### Эндпоинты

| Метод и путь | Доступ | Назначение |
|---|---|---|
| `GET /health` | без токена | 200 `{"status": "healthy", "model_version": "lab2-v1"}` — модель загружена и проверена, токен задан; иначе 503 `{"status": "unavailable"}` без подробностей |
| `POST /predict` | `Authorization: Bearer <API_TOKEN>` | предсказание |
| `GET /metrics` | `Authorization: Bearer <METRICS_TOKEN>` | метрики Prometheus; без `METRICS_TOKEN` эндпоинт выключен (404) |
| `GET /`, `/static/*` | без токена | веб-страница |

### Схема запроса `/predict`

```
POST /predict
Content-Type: application/json            (charset — только utf-8)
Authorization: Bearer <API_TOKEN>

{"text": "How do I bake chocolate chip cookies?"}
```

Правила — те же, что при оценке модели (`src/predict.py: validate_input`):

- тело — JSON-объект с единственным обязательным полем `text`; лишние поля и пакеты (массивы) отклоняются;
- `text` — строка, не пустая и не из одних пробелов, не длиннее 10 000 символов;
- `null`, числа, `NaN`, `Infinity`, списки вместо строки не допускаются; `NaN`/`Infinity` и
  повторяющиеся ключи отклоняются уже на разборе JSON;
- текст должен содержать хотя бы одно слово из словаря модели, иначе классификация невозможна.

Ответ 200:

```json
{"prediction": "malicious", "label": 1, "model_version": "lab2-v1",
 "request_id": "3f0c…"}
```

`prediction` — `benign` или `malicious`, `label` — 0 или 1. Вероятность не возвращается:
используемый классификатор не даёт откалиброванной оценки, а произвольный score нельзя называть вероятностью.
`request_id` генерирует сервер (UUID4); он же возвращается в заголовке `X-Request-ID` и пишется в лог.

### Ошибки

Формат любой ошибки — без traceback, путей и внутренних сообщений:

```json
{"error": {"code": "empty_text", "message": "…"}, "request_id": "…"}
```

| HTTP | `error.code` | Причина |
|---|---|---|
| 400 | `invalid_json` | повреждённый JSON, не UTF-8, `NaN`/`Infinity`, повторяющийся ключ, слишком глубокая вложенность |
| 400 | `invalid_content_length` | нечисловой `Content-Length` |
| 401 | `auth_missing`, `auth_invalid` | нет токена / неверный токен (заголовок `WWW-Authenticate: Bearer`) |
| 401 | `metrics_unauthorized` | нет или неверный токен `/metrics` |
| 404 | `http_404` | неизвестный путь |
| 405 | `http_405` | неверный метод (например, `GET /predict`) |
| 413 | `body_too_large` | тело больше 64 KiB, в том числе при chunked-передаче |
| 413 | `text_too_long` | `text` длиннее 10 000 символов |
| 415 | `unsupported_media_type` | не `application/json` или кодировка не UTF-8 |
| 422 | `invalid_shape`, `missing_field`, `unexpected_field`, `invalid_type`, `empty_text` | нарушена схема ЛР2 |
| 422 | `no_known_features` | в тексте нет ни одного слова из словаря модели |
| 429 | `rate_limited` | превышен лимит запросов на токен (`Retry-After`) |
| 429 | `auth_blocked` | адрес заблокирован после серии неудачных входов (`Retry-After`) |
| 500 | `internal_error` | непредвиденная ошибка (подробности — только в логе сервера) |
| 503 | `model_unavailable`, `service_unavailable` | модель не готова / сервис не настроен |
| 503 | `busy` | все слоты предсказания заняты дольше 0.5 с (`Retry-After: 1`) |
| 504 | `timeout` | предсказание не завершилось за 2 с |

Порядок проверок в `/predict`: готовность → блокировка адреса и токен (429/401) → Content-Type (415) →
размер тела при потоковом чтении (413) → JSON (400) → схема ЛР2 (422/413) → слот (503) → модель (504).
Все отказы до последнего шага происходят до вызова модели; тесты проверяют это фикстурой
`forbid_model`, а сценарий обнаружения — по неизменному `api_predictions_total`.

### Пределы и их обоснование

| Параметр | Значение | Переменная | Обоснование |
|---|---|---|---|
| Длина текста | 10 000 символов | — (`src/predict.py`) | политика входа ЛР2 (та же, что при оценке модели); больший текст не улучшает TF-IDF-признаки, но увеличивает время обработки |
| Размер тела | 65 536 байт (64 KiB) | `MAX_BODY_BYTES` | 10 000 символов × до 4 байт UTF-8 = 40 000 байт плюс JSON-обёртка с запасом. Тело читается по частям и обрывается при превышении, поэтому в память не попадает больше лимита; `Content-Length` — только ранняя проверка |
| Параллельные предсказания | 4 | `MAX_CONCURRENT` | контейнер ограничен 1 CPU; предсказание занимает миллисекунды, больше потоков не ускоряет обработку, а только увеличивает память |
| Ожидание слота | 0.5 с | `QUEUE_TIMEOUT` | очередь не растёт бесконечно: при перегрузке клиент быстро получает 503 `busy` |
| Время предсказания | 2 с | `INFERENCE_TIMEOUT` | обычное время — единицы миллисекунд; 2 с — с запасом в сотни раз |
| Запросы на токен | 30 за 60 с | `RATE_LIMIT`, `RATE_WINDOW` | ручная работа со страницей укладывается с запасом; массовая выгрузка предсказаний — нет |
| Неудачные входы с адреса | 10 за 60 с → блокировка до конца окна | `AUTH_FAIL_LIMIT`, `AUTH_FAIL_WINDOW` | опечатки не блокируют, перебор токена (≥ 32 символа, `secrets.token_urlsafe(32)`) становится бессмысленным |
| Соединения uvicorn | 32 | `--limit-concurrency` (Dockerfile) | сверх лимита uvicorn сам отвечает 503, не доходя до приложения |
| Keep-alive | 5 с | `--timeout-keep-alive` | простаивающие соединения не держат ресурсы |

Ограничение тела при JSON-экранировании: клиент, который кодирует символы вне BMP как `\uXXXX\uXXXX`
(12 байт на символ), упрётся в 64 KiB раньше 10 000 символов. Кириллица в виде `\uXXXX` (6 байт) укладывается.

### Освобождение ресурсов

Клиентский тайм-аут сам по себе не останавливает вычисление, а поток Python нельзя прервать снаружи.
Поэтому (`src/api/limits.py`):

- предсказание выполняется в отдельном потоке и занимает один из 4 слотов семафора;
- через 2 с клиент получает 504, но поток продолжает работу до конца;
- слот освобождается в `finally` внутри потока — только когда вычисление действительно завершилось.

Так число одновременно работающих вычислений никогда не превышает `MAX_CONCURRENT`, даже если клиенты
обрывают соединения. Новые запросы при занятых слотах получают 503 `busy`, а не встают в бесконечную очередь.

### Аутентификация и rate limiting

- Механизм: один API-токен, заголовок `Authorization: Bearer <token>`. Ролей нет, поэтому 403 не используется.
- Серверный токен — из файла `API_TOKEN_FILE` (приоритет) или переменной `API_TOKEN`; в Git и образе его нет.
  Минимальная длина — 32 символа. Сравнение — за постоянное время (`hmac.compare_digest`).
- Токен не пишется в логи и ответы; в отчёте показываются только замаскированные значения.
- Ключи лимитов: частота запросов — по токену (префикс его SHA256, сам токен не хранится);
  неудачные входы — по IP-адресу клиента из TCP-соединения.
- `X-Forwarded-For` не используется: proxy нет, uvicorn запускается с `--no-proxy-headers`. Иначе при
  запросах с `127.0.0.1` подбирающий токен мог бы обходить блокировку, подставляя заголовок.
- `/metrics` защищён отдельным токеном `METRICS_TOKEN`, совместимым с `bearer_token_file`/`authorization`
  в конфигурации Prometheus.

Ограничения limiter в памяти процесса:

- у каждого worker свои счётчики, поэтому сервис запускается с `--workers 1`; при N workers фактический лимит
  до N раз выше;
- при перезапуске процесса счётчики и блокировки сбрасываются;
- за Docker NAT или общим proxy у всех клиентов может быть один адрес, и блокировка по адресу затронет всех.

Для production нужен общий счётчик (например, Redis) или лимиты на reverse proxy.

### Способ доступа

Сервис слушает только loopback ВМ (`127.0.0.1:8000`, в Docker — `-p 127.0.0.1:8000:8000`).
HTTPS не настроен, поэтому токен по открытой сети не передаётся. Доступ с хост-машины — через SSH-туннель:

```bash
ssh -N -L 8000:127.0.0.1:8000 mluser@<IP ВМ>
# затем в браузере хоста: http://127.0.0.1:8000/
```

### Веб-страница

Страница отдаётся тем же приложением (тот же origin), поэтому CORS не настраивается.

- Токен вводится вручную в поле типа password, читается в момент отправки и нигде не сохраняется
  (нет `localStorage`, cookie, URL); в HTML и JavaScript токена нет.
- Ответ сервера выводится через `textContent`, без `innerHTML`.
- Показываются состояния: ожидание, результат, ошибка валидации, нет доступа, превышение лимита
  (с `Retry-After`), недоступность сервиса. Сообщения — собственные по `error.code`, тексты сервера не выводятся.
- Ограничения в браузере (длина текста) — только подсказка; проверяет сервер.
- Заголовки ответов: `Content-Security-Policy: default-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`,
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`.

### Логи

Одна JSON-строка на событие в stdout. Пример лога запроса:

```json
{"ts": "…", "level": "WARNING", "logger": "api.request", "event": "request",
 "request_id": "…", "method": "POST", "route": "/predict", "status": 401,
 "duration_ms": 0.41, "model_version": "lab2-v1", "outcome": "rejected",
 "reject_reason": "auth_invalid"}
```

- `outcome`: `ok` (INFO), `rejected` (WARNING, с `reject_reason`), `error` (ERROR).
- Текст запроса, токены, IP-адреса, User-Agent и query string не пишутся. Access-лог uvicorn отключён:
  он содержит IP и строку запроса.
- События старта: `model_loaded` (версия и префикс SHA256), `model_not_ready` (причина), `not_ready` (нет токена),
  `metrics_disabled`.

### Метрики

| Метрика | Labels | Что показывает |
|---|---|---|
| `api_requests_total` | `route`, `method`, `status_class` (2xx/4xx/5xx) | количество запросов и ошибок |
| `api_request_duration_seconds` | `route` | распределение времени ответа (гистограмма, 5 мс — 5 с) |
| `api_rejections_total` | `reason` | отказы валидации, аутентификации, лимитов (значения — `error.code`) |
| `api_predictions_total` | `prediction` | выполненные предсказания по классам |
| `model_ready` | — | 1 — модель загружена и сервис настроен |
| `model_info` | `version` | развёрнутая версия модели |

Labels берутся только из фиксированных множеств: неизвестные маршруты — `other`, неизвестные причины — `other`.
`request_id`, текст и адреса в labels не используются, поэтому число временных рядов не зависит от клиентов.

```bash
curl -s -H "Authorization: Bearer $(cat ~/.config/ml-project/metrics_token)" \
  http://127.0.0.1:8000/metrics | grep -E '^api_rejections_total'
```

### Что видит приложение, а что — нет

Reverse proxy в проекте нет: внешний слой — сам uvicorn. Часть запросов он отклоняет, не передавая
приложению, и такие отказы не попадают в `api_requests_total` и логи `api.request`:

- некорректный HTTP-запрос (400 от парсера h11);
- превышение `--limit-concurrency 32` (503 от uvicorn).

Они видны только в служебном логе uvicorn (`uvicorn.error`, тоже JSON). Если перед сервисом поставить
nginx/Traefik, его отказы (лимит тела, TLS, лимиты соединений) нужно собирать отдельно, из логов и метрик proxy.

### Тесты

```bash
python -m pytest -q
```

Тесты API (`tests/test_api_*.py`) используют `TestClient` FastAPI и покрывают: `/health` 200 и 503
(несовпадение SHA256, отсутствующая или повреждённая модель, нет токена), корректный `/predict`, загрузку
страницы, заголовки безопасности и отсутствие CORS, коды ошибок 400/401/404/413/415/422/429/500,
`Retry-After`, игнорирование `X-Forwarded-For`, 504 `timeout` с удержанием слота до конца вычисления,
формат логов (нет текста и токена), защиту `/metrics` и ограниченность labels. Для отклонённых входов
проверяется, что модель не вызывалась.

Проверки против запущенного сервиса (локально или в контейнере):

```bash
API_TOKEN_FILE=~/.config/ml-project/api_token scripts/api_checks.sh | tee reports/api_checks.txt
```

Проверки 429 идут последними и исчерпывают лимиты: повторный запуск — после конца окна.
Для повторов удобно запускать сервер с `RATE_WINDOW=10 AUTH_FAIL_WINDOW=10`.

### Сценарий обнаружения

Сценарий — подбор API-токена (`scripts/detection_scenario.py`).

Сервер запускается с малыми тестовыми лимитами `AUTH_FAIL_LIMIT=5 AUTH_FAIL_WINDOW=10 RATE_WINDOW=10`.

1. Baseline: `/health` и 3 корректных `/predict`, снимок `/metrics`.
2. Атака: 15 запросов с неверными токенами с интервалом 0.2 с (≈ 3 с). Ожидается 5 × 401, затем 429 `auth_blocked`;
   корректный токен с того же адреса во время блокировки тоже получает 429.
3. Снимок `/metrics`, проверка правила.
4. Восстановление: ожидание 11 с (конец окна), корректный `/predict` → 200, новых отказов аутентификации нет.

Правило обнаружения (выражение PromQL, алерт `ApiAuthBruteforce`):

```
increase(api_rejections_total{reason=~"auth_missing|auth_invalid|auth_blocked"}[1m]) > 5
```

Сценарий короче минуты, поэтому скрипт считает `increase` как разницу снимков до и после атаки.

```bash
# терминал 1
API_TOKEN_FILE=~/.config/ml-project/api_token METRICS_TOKEN_FILE=~/.config/ml-project/metrics_token \
AUTH_FAIL_LIMIT=5 AUTH_FAIL_WINDOW=10 RATE_WINDOW=10 \
  uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --no-proxy-headers

# терминал 2
API_TOKEN_FILE=~/.config/ml-project/api_token METRICS_TOKEN_FILE=~/.config/ml-project/metrics_token \
  python scripts/detection_scenario.py
```

Результаты — в `reports/detection/`: `metrics_before.txt`, `metrics_after.txt`, `metrics_recovery.txt`,
`detection.json` (временной интервал, прирост счётчиков, срабатывание правила, итоги проверок).
Код возврата 0 — все ожидания выполнены. Токены скрипт читает из файлов и не выводит.

Ограничения: правило видит поведение API, а не атаку на модель. Оно не отличает подбор токена от
неправильно настроенного клиента, не видит медленный перебор ниже порога и отказы uvicorn/proxy,
а за NAT не различает клиентов. Метрики сбрасываются при перезапуске процесса.

## Docker

- Базовый образ `python:3.14.4-slim`, зафиксирован по digest; только runtime-зависимости
  (`requirements-runtime.txt`, установка с `--no-deps` и `pip check`).
- Пользователь `app` (UID 10001) без пароля и домашней папки; файлы приложения принадлежат root
  и доступны ему только на чтение.
- `.dockerignore` по белому списку: в образ попадают только код сервиса, `static/`, `metrics/baseline.json`
  и `models/baseline.joblib` (модель ЛР2, версия `lab2-v1`). Секретов в образе нет.
- `HEALTHCHECK` опрашивает `/health`: при 503 контейнер становится `unhealthy`.
- Порт 8000 внутри контейнера (`0.0.0.0` — интерфейс контейнера); на хосте публикуется только на `127.0.0.1`.
- Обновлён `perl-base` для закрытия CVE-2026-13221, CVE-2026-42496, CVE-2026-8376 (CRITICAL, найдены Trivy).

Секреты передаются при запуске через `--env-file` (шаблон — `.env.example`). Файл лежит вне репозитория:

```bash
umask 077
{
  echo "API_TOKEN=$(cat ~/.config/ml-project/api_token)"
  echo "METRICS_TOKEN=$(cat ~/.config/ml-project/metrics_token)"
} > ~/.config/ml-project/lab4.env
```

`--env-file` выбран потому, что файлы токенов принадлежат пользователю хоста (UID 1000, права 600) и
недоступны пользователю 10001 в контейнере. Ограничение: переменные окружения видны в `docker inspect`
тем, у кого есть доступ к Docker; в production — Docker secrets или хранилище секретов.

```bash
docker build -t ml-project:lab4 .

docker run -d --name ml-api -p 127.0.0.1:8000:8000 \
  --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges \
  --memory 512m --cpus 1 --pids-limit 128 \
  --env-file ~/.config/ml-project/lab4.env \
  ml-project:lab4

docker ps                                    # STATUS: Up … (healthy)
docker exec ml-api id -u                     # 10001
curl -i http://127.0.0.1:8000/health         # 200 healthy
docker logs ml-api 2>&1 | tail -5            # JSON-логи
docker rm -f ml-api
```

Лимиты меняются переменными окружения (`-e RATE_WINDOW=10` и т.п., список — в таблице пределов и `.env.example`).

## CI

`.github/workflows/ci.yml` запускается на каждый push и pull request. Этапы идут
по порядку; если этап упал, следующие не выполняются (skipped), но отчёты
сохраняются (`if: always()`), а итоговый статус остаётся failed.

1. Код (`actions/checkout`) и модель baseline ЛР2 из GitHub Release с проверкой SHA256
   по `metrics/baseline.json`.
2. Зависимости из `requirements.txt`; инструменты (Ruff, pip-audit) с фиксированными версиями.
3. Данные с Hugging Face с проверкой SHA256 (`python -m src.data fetch`).
4. Ruff (`src/`, `tests/`, `scripts/`) и Bandit.
5. Тесты pytest, включая тесты API.
6. pip-audit для `requirements.txt` и отдельно для `requirements-runtime.txt`.
7. Data quality gate (`configs/data_rules.yaml`).
8. Обучение и оценка кандидата, model quality gate (`configs/model_gate.yaml`). В ЛР4 образ содержит
   зафиксированную модель ЛР2, поэтому эти шаги подтверждают воспроизводимость модели из кода и данных.
9. Сборка образа, проверка UID ≠ 0.
10. Trivy image (CRITICAL) и Trivy config (Dockerfile).
11. API-контейнер: токены генерируются на один прогон и маскируются в логе (`::add-mask::`), контейнер
    запускается с ограничениями (`--read-only`, `--cap-drop ALL`, `no-new-privileges`, лимиты памяти, CPU и процессов);
    smoke `/health`, статус `HEALTHCHECK`, `Config.User` и `id -u`; `scripts/api_checks.sh`; после перезапуска —
    сценарий обнаружения; логи контейнера сохраняются, контейнер удаляется.
12. Сохранение отчётов: `reports/` (в том числе `api_checks.txt`, `detection/`, `container.log`),
    сведения о commit и SHA256 модели в образе (`run-info.txt`).

### Политики

| Gate | Правило | Где задано |
|---|---|---|
| Lint / SAST | любая находка Ruff или Bandit — отказ | `pyproject.toml` |
| Тесты | любой упавший тест — отказ | `tests/` |
| Зависимости | строгая политика: любая находка pip-audit — отказ, независимо от severity (неизвестная severity не считается безопасной) | `ci.yml` |
| Данные | поля и типы, NaN/Inf и тексты по политике ЛР2 (`validate_input`), `label ∈ {0,1}`, ≥ 5000 строк, доля класса 1 в [0.50, 0.70], SHA256 | `configs/data_rules.yaml` |
| Модель | F1-macro кандидата ≥ baseline × 0.95 (0.9499 × 0.95 = 0.9024); та же версия данных и то же разбиение; отсутствующая или нечисловая метрика — отказ | `configs/model_gate.yaml` |
| Образ | любая CRITICAL уязвимость в образе — отказ; ошибки конфигурации Dockerfile — отказ; ошибка сканирования — отказ | `ci.yml` |
| API-контейнер | не healthy, UID 0, расхождение в `api_checks.sh` или в сценарии обнаружения — отказ | `ci.yml`, `scripts/` |

Baseline (`metrics/baseline.json`) только читается и не перезаписывается метриками кандидата.
CI-контроль на фиксированной тестовой выборке не заменяет финальную независимую оценку модели.

### Безопасность CI

- `permissions: contents: read`; триггер `pull_request`, а не `pull_request_target`.
- Секретов репозитория нет: данные и модель публичные. Токены API создаются на один прогон в `$RUNNER_TEMP`,
  маскируются в логе и не попадают в отчёты. В Dockerfile и build arguments секретов нет.
- Actions зафиксированы по SHA коммита; `persist-credentials: false`.
- Trivy 0.76.1 ставится из официального релиза с проверкой checksum, без `trivy-action`
  (после компрометации trivy-action и Trivy v0.69.4 в марте 2026).
- Тайм-ауты на job и на долгие шаги; переменные GitHub в скриптах берутся из окружения, а не через `${{ }}`.

## Локальная проверка

```bash
python -m src.data fetch
ruff check src/ tests/ scripts/
python -m bandit -r src/
python -m pytest -q
pip-audit -r requirements.txt
pip-audit -r requirements-runtime.txt
python -m src.data_gate
python -m src.evaluate && python -m src.model_gate
docker build -t ml-project:lab4 .
trivy image --severity CRITICAL --exit-code 1 ml-project:lab4
trivy config --exit-code 1 Dockerfile
```
