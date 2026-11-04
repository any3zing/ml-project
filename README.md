# ML Project

Учебный проект по дисциплине «Киберустойчивость систем ИИ».
Задача: бинарная классификация текста — `0` benign, `1` malicious (prompt injection).

## Структура проекта

- `configs/data_source.yaml` — источник данных, зафиксированная ревизия и SHA256
- `src/` — весь код, используемый для получения модели:
  - `data.py` — скачивание, проверка SHA256, разбиение train/test
  - `preprocess.py` — TF-IDF с параметрами, выбранными в ЛР2
  - `train.py` — сборка и обучение Pipeline
  - `metrics.py` — метрики качества
  - `evaluate.py` — обучение и оценка одной командой
  - `artifacts.py`, `integrity.py` — сохранение и загрузка модели с проверкой SHA256
  - `predict.py` — валидация входа и предсказание
- `metrics/baseline.json` — baseline ЛР2 (не перезаписывается автоматически)
- `notebooks/` — исследование и подбор гиперпараметров (импортирует код из `src/`)
- `tests/` — автоматические тесты
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

Подбор гиперпараметров (GridSearchCV) — исследовательская часть, выполнена в `notebooks/Lab2.ipynb`;
выбранные параметры зафиксированы в `src/preprocess.py` и `src/train.py`.

## Тестирование и статический анализ

```bash
python -m pytest tests/ -q
python -m bandit -r src/
```

## Предсказание

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


### Последовательность pipeline

`.github/workflows/ci.yml` запускается на каждый push и pull request. Этапы идут
по порядку; если этап упал, следующие не выполняются (skipped), но отчёты
сохраняются (`if: always()`), а итоговый статус остаётся failed.

1. Код (`actions/checkout`) и модель baseline ЛР2 из GitHub Release с проверкой SHA256
   по `metrics/baseline.json`.
2. Зависимости из `requirements.txt`; инструменты (Ruff, pip-audit) с фиксированными версиями.
3. Данные с Hugging Face с проверкой SHA256 (`python -m src.data fetch`).
4. Ruff (`pyproject.toml`) и Bandit.
5. Тесты pytest.
6. Аудит зависимостей pip-audit.
7. Data quality gate (`configs/data_rules.yaml`).
8. Обучение и оценка кандидата, model quality gate (`configs/model_gate.yaml`).
9. Сборка образа, проверка UID ≠ 0.
10. Trivy image (CRITICAL) и Trivy config (Dockerfile), smoke-проверка контейнера.
11. Сохранение отчётов: `reports/`, SHA256 модели, сведения о commit (`run-info.txt`).

### Политики

| Gate | Правило | Где задано |
|---|---|---|
| Lint / SAST | любая находка Ruff или Bandit — отказ | `pyproject.toml` |
| Тесты | любой упавший тест — отказ | `tests/` |
| Зависимости | строгая политика: любая находка pip-audit — отказ, независимо от severity (неизвестная severity не считается безопасной) | `ci.yml` |
| Данные | поля и типы, NaN/Inf и тексты по политике ЛР2 (`validate_input`), `label ∈ {0,1}`, ≥ 5000 строк, доля класса 1 в [0.50, 0.70], SHA256 | `configs/data_rules.yaml` |
| Модель | F1-macro кандидата ≥ baseline × 0.95 (0.9499 × 0.95 = 0.9024); та же версия данных и то же разбиение; отсутствующая или нечисловая метрика — отказ | `configs/model_gate.yaml` |
| Образ | любая CRITICAL уязвимость в образе — отказ; ошибки конфигурации Dockerfile — отказ; ошибка сканирования — отказ | `ci.yml` |

Baseline (`metrics/baseline.json`) только читается и не перезаписывается метриками кандидата.
CI-контроль на фиксированной тестовой выборке не заменяет финальную независимую оценку модели.

### Безопасность CI

- `permissions: contents: read`; триггер `pull_request`, а не `pull_request_target`.
- Секретов в проекте нет: данные и модель публичные, токены не нужны и не создавались.
  В Dockerfile и build arguments секретов нет.
- Actions зафиксированы по SHA коммита; `persist-credentials: false`.
- Trivy 0.76.1 ставится из официального релиза с проверкой checksum, без `trivy-action`
  (после компрометации trivy-action и Trivy v0.69.4 в марте 2026).
- Тайм-ауты на job и на долгие шаги; переменные GitHub в скриптах берутся из окружения, а не через `${{ }}`.

### Docker

- Базовый образ `python:3.14.4-slim`, зафиксирован по digest; только runtime-зависимости (`requirements-runtime.txt`).
- Пользователь `app` (UID 10001) без пароля и домашней папки; файлы приложения принадлежат root и доступны ему только на чтение.
- `.dockerignore` по белому списку: в образ попадают только нужные модули `src/` и `models/candidate.joblib` с `.sha256`.
- Обновлён `perl-base` для закрытия CVE-2026-13221, CVE-2026-42496, CVE-2026-8376 (CRITICAL, найдены Trivy).

```bash
docker build -t ml-project:lab3 .
docker run --rm --entrypoint id ml-project:lab3 -u        # 10001
docker run --rm --read-only --cap-drop ALL \
  --security-opt no-new-privileges --network none ml-project:lab3   # SMOKE: OK
```

### Локальная проверка

```bash
python -m src.data fetch
ruff check src/ tests/
python -m bandit -r src/
python -m pytest -q
pip-audit -r requirements.txt
python -m src.data_gate
python -m src.evaluate && python -m src.model_gate
docker build -t ml-project:lab3 .
trivy image --severity CRITICAL --exit-code 1 ml-project:lab3
trivy config --exit-code 1 Dockerfile
```
