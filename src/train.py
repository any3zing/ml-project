"""Обучение базового текстового классификатора."""

from time import perf_counter

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline


def train_model(X_train, y_train, seed=42):
    vectorizer = TfidfVectorizer(
        lowercase=True,
        ngram_range=(1, 2),
        min_df=2,
        max_features=20_000,
        sublinear_tf=True,
    )

    X_train_tfidf = vectorizer.fit_transform(X_train)

    model = LogisticRegression(
        C=1.0,
        solver="liblinear",
        max_iter=1000,
        random_state=seed,
    )

    start = perf_counter()
    model.fit(X_train_tfidf, y_train)
    training_seconds = perf_counter() - start

    pipeline = Pipeline([
        ("tfidf", vectorizer),
        ("classifier", model),
    ])

    return pipeline, training_seconds