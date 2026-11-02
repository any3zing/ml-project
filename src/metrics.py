"""Метрики качества бинарного классификатора."""

import math

from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)

LABELS = (0, 1)
TARGET_NAMES = ("benign", "malicious")


def _rate(numerator, denominator):
    return float(numerator / denominator) if denominator else math.nan


def compute_metrics(y_true, y_pred):
    """Считает метрики; метки должны быть только 0 и 1."""
    y_true = [int(value) for value in y_true]
    y_pred = [int(value) for value in y_pred]

    if len(y_true) != len(y_pred) or not y_true:
        raise ValueError("y_true и y_pred должны быть непустыми и одной длины.")
    if not set(y_true) | set(y_pred) <= set(LABELS):
        raise ValueError("Допустимы только метки 0 и 1.")

    cm = confusion_matrix(y_true, y_pred, labels=list(LABELS))
    tn, fp, fn, tp = (int(value) for value in cm.ravel())

    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "f1_macro": float(
            f1_score(y_true, y_pred, average="macro", zero_division=0)
        ),
        "false_positive_rate": _rate(fp, tn + fp),
        "false_negative_rate": _rate(fn, fn + tp),
        "confusion_matrix": [[tn, fp], [fn, tp]],
        "support": len(y_true),
        "classification_report": classification_report(
            y_true,
            y_pred,
            labels=list(LABELS),
            target_names=list(TARGET_NAMES),
            output_dict=True,
            zero_division=0,
        ),
    }
