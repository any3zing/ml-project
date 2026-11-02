"""Получение, проверка целостности и разбиение данных.

Командная строка:
    python -m src.data fetch    # скачать датасет и проверить SHA256
    python -m src.data verify   # проверить уже скачанный датасет
"""

import argparse
import sys
import tempfile
from pathlib import Path

import pandas as pd
import requests
import yaml
from sklearn.model_selection import train_test_split

from src.integrity import IntegrityError, sha256_file, verify_sha256
from src.paths import DATA_DIR, DATA_SOURCE_CONFIG, resolve

REQUEST_TIMEOUT = (10, 60)  # соединение, чтение — секунды


class DataError(RuntimeError):
    """Данные не соответствуют ожидаемой версии или структуре."""


def load_config(path=DATA_SOURCE_CONFIG):
    """Читает конфигурацию источника данных (безопасный YAML-загрузчик)."""
    with Path(path).open(encoding="utf-8") as file:
        return yaml.safe_load(file)


def _file_url(dataset_cfg, file_path):
    url = (
        f"{dataset_cfg['base_url']}/{dataset_cfg['name']}"
        f"/resolve/{dataset_cfg['revision']}/{file_path}"
    )
    if not url.startswith("https://"):
        raise DataError("Разрешены только HTTPS-источники данных.")
    return url


def _download(url, destination, max_bytes):
    """Скачивает файл во временный файл с ограничением размера."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    received = 0

    with requests.get(url, stream=True, timeout=REQUEST_TIMEOUT) as response:
        response.raise_for_status()
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, delete=False
        ) as tmp:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                received += len(chunk)
                if received > max_bytes:
                    tmp.close()
                    Path(tmp.name).unlink(missing_ok=True)
                    raise DataError(
                        f"Файл {url} превышает лимит {max_bytes} байт."
                    )
                tmp.write(chunk)

    Path(tmp.name).replace(destination)


def fetch_dataset(config=None, *, raw_dir=None, force=False):
    """Скачивает части датасета, проверяет хэши и собирает CSV.

    Возвращает путь к итоговому CSV. При любом несовпадении хэша
    вызывает IntegrityError; частично проверенные данные не используются.
    """
    config = config or load_config()
    dataset_cfg = config["dataset"]
    output = resolve(dataset_cfg["output"])
    raw_dir = Path(raw_dir) if raw_dir else DATA_DIR / "raw"

    if output.exists() and not force:
        verify_sha256(output, dataset_cfg["output_sha256"])
        return output

    parts = []
    for item in dataset_cfg["files"]:
        local = raw_dir / item["path"]
        if not local.exists() or force:
            _download(
                _file_url(dataset_cfg, item["path"]),
                local,
                dataset_cfg["max_file_bytes"],
            )
        verify_sha256(local, item["sha256"])
        parts.append(pd.read_parquet(local))

    output.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(parts, ignore_index=True).to_csv(output, index=False)
    verify_sha256(output, dataset_cfg["output_sha256"])
    return output


def load_dataset(path=None, *, config=None):
    """Загружает CSV только после проверки SHA256 и числа строк."""
    config = config or load_config()
    dataset_cfg = config["dataset"]
    path = resolve(path or dataset_cfg["output"])

    verify_sha256(path, dataset_cfg["output_sha256"])
    df = pd.read_csv(path)

    if len(df) != dataset_cfg["rows"]:
        raise DataError(
            f"Ожидалось {dataset_cfg['rows']} строк, получено {len(df)}."
        )
    return df


def make_strata(df, columns):
    """Строит метку страты из нескольких столбцов."""
    return df[columns].astype(str).agg("__".join, axis=1)


def split_dataset(df, *, seed=42, test_fraction=0.2, stratify=("source", "label")):
    """Воспроизводимое стратифицированное разбиение train/test."""
    strata = make_strata(df, list(stratify))
    if strata.value_counts().min() < 2:
        raise DataError("В одной из страт меньше двух объектов.")

    train_df, test_df = train_test_split(
        df,
        test_size=test_fraction,
        random_state=seed,
        shuffle=True,
        stratify=strata,
    )

    if not set(train_df.index).isdisjoint(test_df.index):
        raise DataError("Обучающая и тестовая выборки пересекаются.")

    return train_df.copy(), test_df.copy()


def split_from_config(df, config=None):
    """Разбиение с параметрами из конфигурации и проверкой размеров."""
    config = config or load_config()
    split_cfg = config["split"]
    train_df, test_df = split_dataset(
        df,
        seed=split_cfg["seed"],
        test_fraction=split_cfg["test_fraction"],
        stratify=split_cfg["stratify"],
    )
    if (len(train_df), len(test_df)) != (
        split_cfg["expected_train_rows"],
        split_cfg["expected_test_rows"],
    ):
        raise DataError(
            f"Неожиданные размеры выборок: {len(train_df)}/{len(test_df)}."
        )
    return train_df, test_df


def main(argv=None):
    parser = argparse.ArgumentParser(description="Данные проекта")
    parser.add_argument("command", choices=["fetch", "verify"])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.command == "fetch":
            path = fetch_dataset(force=args.force)
        else:
            path = resolve(load_config()["dataset"]["output"])
            load_dataset(path)
    except (IntegrityError, DataError, requests.RequestException, OSError) as error:
        print(f"ОШИБКА: {error}", file=sys.stderr)
        return 1

    print(f"OK: {path} sha256={sha256_file(path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
