"""Обучение текстового классификатора с выбранными гиперпараметрами."""

from time import perf_counter

from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from src.preprocess import make_vectorizer

CLASSIFIER_PARAMS = {
    "C": 2.0,
    "solver": "liblinear",
    "max_iter": 2000,  # как в GridSearchCV ЛР2
}


def build_pipeline(seed=42, **vectorizer_overrides):
    """Собирает необученный Pipeline: TF-IDF + логистическая регрессия."""
    return Pipeline([
        ("tfidf", make_vectorizer(**vectorizer_overrides)),
        ("classifier", LogisticRegression(**CLASSIFIER_PARAMS, random_state=seed)),
    ])


def train_model(X_train, y_train, seed=42, **vectorizer_overrides):
    """Обучает Pipeline; возвращает (pipeline, время обучения в секундах)."""
    pipeline = build_pipeline(seed, **vectorizer_overrides)
    start = perf_counter()
    pipeline.fit(X_train, y_train)
    return pipeline, perf_counter() - start
