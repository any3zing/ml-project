"""Обучение и оценка кандидатной модели без ноутбука.

    python -m src.evaluate
    python -m src.evaluate --model-out models/candidate.joblib \
        --metrics-out reports/candidate_metrics.json

Шаги: проверка данных по SHA256 → разбиение → обучение → оценка
на отложенной выборке → сохранение модели и отчёта с метриками.
"""

import argparse
import json
import os
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

import sklearn

from src.artifacts import save_model
from src.data import DataError, load_config, load_dataset, split_from_config
from src.integrity import IntegrityError
from src.metrics import compute_metrics
from src.paths import PROJECT_ROOT, resolve
from src.preprocess import TFIDF_PARAMS
from src.train import CLASSIFIER_PARAMS, train_model


def _relative(path):
    path = Path(path).resolve()
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def run(model_out, metrics_out, config=None):
    config = config or load_config()
    df = load_dataset(config=config)
    train_df, test_df = split_from_config(df, config)

    seed = config["split"]["seed"]
    pipeline, train_seconds = train_model(
        train_df["text"], train_df["label"], seed=seed
    )
    y_pred = pipeline.predict(test_df["text"])
    metrics = compute_metrics(test_df["label"], y_pred)

    model_sha256 = save_model(pipeline, model_out)

    report = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": os.environ.get("GITHUB_SHA", "local"),
        "data": {
            "name": config["dataset"]["name"],
            "revision": config["dataset"]["revision"],
            "sha256": config["dataset"]["output_sha256"],
            "rows": len(df),
        },
        "split": {
            **config["split"],
            "train_size": len(train_df),
            "test_size": len(test_df),
        },
        "model": {
            "path": _relative(model_out),
            "sha256": model_sha256,
            "tfidf": {**TFIDF_PARAMS, "ngram_range": list(TFIDF_PARAMS["ngram_range"])},
            "classifier": CLASSIFIER_PARAMS,
            "train_seconds": round(train_seconds, 3),
        },
        "environment": {
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
        },
        "metrics": metrics,
    }

    metrics_out = Path(metrics_out)
    metrics_out.parent.mkdir(parents=True, exist_ok=True)
    metrics_out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Обучение и оценка модели")
    parser.add_argument("--model-out", default="models/candidate.joblib")
    parser.add_argument("--metrics-out", default="reports/candidate_metrics.json")
    args = parser.parse_args(argv)

    try:
        report = run(resolve(args.model_out), resolve(args.metrics_out))
    except (IntegrityError, DataError, OSError) as error:
        print(f"ОШИБКА: {error}", file=sys.stderr)
        return 1

    metrics = report["metrics"]
    print(f"F1-macro: {metrics['f1_macro']:.4f}")
    print(f"Accuracy: {metrics['accuracy']:.4f}")
    print(f"SHA256 модели: {report['model']['sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
