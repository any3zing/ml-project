"""Предобработка текста: TF-IDF с параметрами, выбранными в ЛР2."""

from sklearn.feature_extraction.text import TfidfVectorizer

# Параметры выбраны GridSearchCV в ЛР2 (см. metrics/baseline.json).
TFIDF_PARAMS = {
    "analyzer": "word",
    "lowercase": True,
    "ngram_range": (1, 3),
    "min_df": 2,
    "max_features": 30_000,
    "sublinear_tf": True,
}


def make_vectorizer(**overrides):
    """Создаёт TF-IDF-векторизатор; overrides — только для тестов."""
    return TfidfVectorizer(**{**TFIDF_PARAMS, **overrides})
