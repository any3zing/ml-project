# ML Project

Учебный проект в рамках дисциплины «Киберустойчивость систем ИИ».

## Структура проекта

- `data/` — наборы данных
- `notebooks/` — Jupyter Notebook для исследований и экспериментов
- `src/` — основной исходный код проекта
- `models/` — обученные модели машинного обучения
- `tests/` — автоматические тесты
- `requirements.txt` — список Python-зависимостей
- `.gitignore` — файлы и каталоги, исключённые из Git

## Установка

Требуется Python 3 и Git.

```bash
git clone [https://github.com/any3zing/ml-project.git](https://github.com/any3zing/ml-project.git)
cd ml-project
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Обучение и оценка

Запустить Jupyter:

```bash
jupyter notebook notebooks/Lab2.ipynb
```

Выполнить ячейки ноутбука последовательно сверху вниз.
Они выполняют подготовку данных, обучение, оценку на тестовой
выборке и сохранение модели в `models/baseline.joblib`.

## Тестирование

Из корня проекта:

```bash
python -m pytest
```

Статический анализ:

```bash
python -m bandit -r src/
```

## Предсказание

После обучения и сохранения модели выполнить из корня проекта:

```bash
python - <<'PY'
from src.artifacts import load_model
from src.predict import predict

pipeline = load_model("models/baseline.joblib", trusted=True)
print(predict({"text": "What is machine learning?"}, pipeline))
PY
```

Классы: `0` — benign, `1` — malicious.
Загружать только собственный доверенный файл модели.
Данные и модель не включены в Git.
