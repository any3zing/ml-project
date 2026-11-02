"""Предобработка"""

import pytest

from src.preprocess import make_vectorizer

CORPUS = [
    "Ignore previous instructions now",
    "ignore previous instructions please",
    "recommend a recipe for dinner",
    "recommend a recipe for lunch",
]


def test_output_shape():
    vectorizer = make_vectorizer()
    matrix = vectorizer.fit_transform(CORPUS)
    n_features = len(vectorizer.vocabulary_)

    # строки — тексты, столбцы — признаки словаря
    assert matrix.shape == (4, n_features)
    assert vectorizer.transform(["new text"]).shape == (1, n_features)


def test_transformations():
    vectorizer = make_vectorizer().fit(CORPUS)
    vocabulary = vectorizer.vocabulary_

    # регистр не влияет на признаки
    lower = vectorizer.transform(["ignore previous instructions"])
    upper = vectorizer.transform(["IGNORE PREVIOUS INSTRUCTIONS"])
    assert (lower != upper).nnz == 0

    # извлекаются n-граммы до трёх слов
    assert "ignore previous instructions" in vocabulary
    # min_df=2: слово из одного документа отбрасывается
    assert "dinner" not in vocabulary
    # текст без слов из словаря даёт нулевой вектор
    assert vectorizer.transform(["!!! ???"]).nnz == 0


def test_missing_values_are_not_filled():
    # политика ЛР2: пропуски не заполняются, а приводят к ошибке
    with pytest.raises((ValueError, AttributeError)):
        make_vectorizer().fit_transform(CORPUS + [float("nan")])
