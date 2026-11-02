"""Пути проекта относительно корня репозитория."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "configs"
DATA_DIR = PROJECT_ROOT / "data"
MODELS_DIR = PROJECT_ROOT / "models"
METRICS_DIR = PROJECT_ROOT / "metrics"
REPORTS_DIR = PROJECT_ROOT / "reports"

DATA_SOURCE_CONFIG = CONFIG_DIR / "data_source.yaml"


def resolve(path):
    """Относительный путь считается от корня проекта."""
    path = Path(path)
    return path if path.is_absolute() else PROJECT_ROOT / path
