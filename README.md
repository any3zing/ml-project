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
