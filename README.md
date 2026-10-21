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
Требуется Python 3 и Git.
```bash
git clone https://github.com/any3zing/ml-project.git
cd ml-project
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
jupyter lab
