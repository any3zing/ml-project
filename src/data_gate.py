"""Data quality gate: проверка данных до обучения и оценки.

Командная строка:
    python -m src.data_gate  # проверить data/dataset.csv
Код возврата: 0 — данные допустимы, 1 — нарушена политика.
"""

import argparse
import json
import sys

import numpy as np
import pandas as pd
import yaml

from src.integrity import sha256_file
from src.paths import CONFIG_DIR, REPORTS_DIR, resolve
from src.predict import InputValidationError, validate_input

DATA_RULES = CONFIG_DIR / "data_rules.yaml"
REPORT = REPORTS_DIR / "data_gate.json"

TYPE_CHECKS = {
    "str": pd.api.types.is_string_dtype,
    "int": pd.api.types.is_integer_dtype,
}


def load_rules(path=DATA_RULES):
    """Читает правила gate (безопасный YAML-загрузчик)."""
    with resolve(path).open(encoding="utf-8") as file:
        return yaml.safe_load(file)


def check_schema(df, rules):
    """Обязательные поля, типы, пропуски и NaN/Inf."""
    missing = [name for name in rules["columns"] if name not in df.columns]
    if missing:
        return [f"нет обязательных полей: {missing}"]

    errors = []
    for name, expected in rules["columns"].items():
        column = df[name]
        if column.isna().any():
            errors.append(f"{name}: пропуски/NaN — {int(column.isna().sum())}")
        if pd.api.types.is_numeric_dtype(column) and np.isinf(column).any():
            errors.append(f"{name}: значения Inf")
        if not TYPE_CHECKS[expected](column):
            errors.append(f"{name}: ожидался тип {expected}, получен {column.dtype}")
    return errors


def check_values(df, rules):
    """Допустимые значения, длина текста, объём и баланс классов."""
    errors = []
    text = df["text"]
    label = df[rules["label"]["column"]]

    if len(df) < rules["min_rows"]:
        errors.append(f"строк {len(df)}, минимум {rules['min_rows']}")

    bad = ~label.isin(rules["label"]["allowed"])
    if bad.any():
        found = label[bad].unique().tolist()[:10]
        errors.append(f"label: недопустимые значения {found}")

    # Политика текста из ЛР2: та же функция, что проверяет запросы к модели
    invalid = 0
    for value in text:
        try:
            validate_input({"text": value})
        except InputValidationError:
            invalid += 1
    if invalid:
        errors.append(f"text: не прошли validate_input (ЛР2) — {invalid}")

    share = float((label == rules["label"]["positive"]).mean())
    low, high = rules["label"]["positive_share"]
    if not low <= share <= high:
        errors.append(f"доля класса 1: {share:.3f}, допустимо [{low}, {high}]")
    return errors


def run_gate(path, rules):
    """Проверяет файл и возвращает отчёт; passed=False — gate не пройден."""
    errors = []
    actual_sha = sha256_file(path)
    if actual_sha != rules["dataset"]["sha256"]:
        errors.append(f"SHA256 не совпадает: {actual_sha}")

    df = pd.read_csv(path)
    schema_errors = check_schema(df, rules)
    errors += schema_errors
    if not schema_errors:  # при сломанной схеме проверки значений бессмысленны
        errors += check_values(df, rules)

    return {
        "path": str(path),
        "sha256": actual_sha,
        "rows": len(df),
        "passed": not errors,
        "errors": errors,
    }


def main(argv=None):
    rules = load_rules()
    parser = argparse.ArgumentParser(description="Data quality gate")
    parser.add_argument("path", nargs="?", default=rules["dataset"]["path"])
    parser.add_argument("--report", default=REPORT)
    args = parser.parse_args(argv)

    try:
        report = run_gate(resolve(args.path), rules)
    except (OSError, pd.errors.ParserError) as error:
        print(f"DATA GATE: FAIL — не удалось прочитать данные: {error}")
        return 1

    report_path = resolve(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for error in report["errors"]:
        print(f"НАРУШЕНИЕ: {error}")
    print("DATA GATE: " + ("OK" if report["passed"] else "FAIL"))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
