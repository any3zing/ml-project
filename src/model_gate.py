"""Model quality gate: сравнение кандидатной модели с baseline ЛР2.

    python -m src.model_gate
Код возврата: 0 — кандидат допущен, 1 — отклонён.
"""

import argparse
import json
import math
import sys

import yaml

from src.paths import CONFIG_DIR, REPORTS_DIR, resolve

POLICY = CONFIG_DIR / "model_gate.yaml"
CANDIDATE = REPORTS_DIR / "candidate_metrics.json"
REPORT = REPORTS_DIR / "model_gate.json"


class GateError(ValueError):
    """Метрика или версия данных не позволяют сравнение."""


def read_json(path):
    with resolve(path).open(encoding="utf-8") as file:
        return json.load(file)


def read_metric(metrics, name, who):
    """Отклоняет отсутствующую, нечисловую и некорректную метрику."""
    value = metrics.get(name)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise GateError(f"{who}: {name} отсутствует или не число ({value!r})")
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise GateError(f"{who}: некорректное значение {name}={value}")
    return float(value)


def check_compatibility(candidate, baseline, policy):
    """Кандидат должен быть оценён на тех же данных и том же разбиении."""
    data_sha = candidate.get("data", {}).get("sha256")
    if data_sha != policy["data_sha256"]:
        raise GateError(f"несовместимая версия данных: {data_sha}")

    split = candidate.get("split", {})
    same_seed = split.get("seed") == baseline["seed"]
    same_size = split.get("test_size") == baseline["split"]["test_size"]
    if not (same_seed and same_size):
        raise GateError("разбиение не совпадает с baseline (seed/test_size)")


def compare(candidate, baseline, policy):
    check_compatibility(candidate, baseline, policy)
    name = policy["metric"]
    base = read_metric(baseline.get("test_metrics", {}), name, "baseline")
    cand = read_metric(candidate.get("metrics", {}), name, "candidate")
    threshold = base * (1 - policy["max_relative_drop"])
    return {
        "metric": name,
        "baseline": base,
        "candidate": cand,
        "threshold": threshold,
        "passed": cand >= threshold,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Model quality gate")
    parser.add_argument("--candidate", default=CANDIDATE)
    parser.add_argument("--policy", default=POLICY)
    parser.add_argument("--report", default=REPORT)
    args = parser.parse_args(argv)

    try:
        with resolve(args.policy).open(encoding="utf-8") as file:
            policy = yaml.safe_load(file)
        baseline = read_json(policy["baseline"])
        candidate = read_json(args.candidate)
        result = compare(candidate, baseline, policy)
    except (GateError, OSError, json.JSONDecodeError, KeyError) as error:
        result = {"passed": False, "error": f"{type(error).__name__}: {error}"}

    result["exit_code"] = 0 if result["passed"] else 1

    report_path = resolve(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if "error" in result:
        print(f"MODEL GATE: FAIL — {result['error']}")
    else:
        verdict = "OK" if result["passed"] else "FAIL"
        print(
            f"MODEL GATE: {verdict} — {result['metric']} "
            f"candidate={result['candidate']:.4f}, "
            f"порог={result['threshold']:.4f} (baseline={result['baseline']:.4f})"
        )
    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())

