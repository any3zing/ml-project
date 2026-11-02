"""Метрики, расчёт на маленьком примере с известным результатом."""

import pytest

from src.metrics import compute_metrics


def test_metrics_known_example():
    # TN=1, FP=1, FN=0, TP=2
    # F1(benign) = 2/3, F1(malicious) = 4/5, F1-macro = (2/3 + 4/5) / 2 = 11/15
    result = compute_metrics([0, 0, 1, 1], [0, 1, 1, 1])

    assert result["confusion_matrix"] == [[1, 1], [0, 2]]
    assert result["accuracy"] == pytest.approx(0.75)
    assert result["f1_macro"] == pytest.approx(11 / 15)
    assert result["false_positive_rate"] == pytest.approx(0.5)
