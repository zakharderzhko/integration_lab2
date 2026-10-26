"""Train the model and persist the resulting artifact."""

from pathlib import Path

import joblib
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

from .model import (
    CAT,
    NUM,
    TARGET,
    load_training_data,
    train_model,
)

ARTIFACTS = (
    Path(__file__).resolve().parent.parent
    / "artifacts"
)

def main() -> None:
    """Train the model, report metrics, and persist the artifact."""

    # 1. Завантажуємо всі дані
    df = load_training_data()

    # 2. Розбиваємо дані: 80% на навчання, 20% на тест
    df_train, df_test = train_test_split(df, test_size=0.2, random_state=42)

    # 3. Отримуємо базову модель
    model = train_model()

    # 4. Перенавчаємо модель ТІЛЬКИ на тренувальній вибірці
    model.fit(df_train[NUM + CAT], df_train[TARGET])

    # 5. Робимо передбачення ТІЛЬКИ для тестової вибірки (тих 20%)
    predictions = model.predict(df_test[NUM + CAT])

    # 6. Рахуємо метрики якості (наскільки добре модель впоралась із тестом)
    r2 = r2_score(df_test[TARGET], predictions)
    mae = mean_absolute_error(df_test[TARGET], predictions)

    print(
        f"[train] Ames TEST evaluation: "
        f"R2={r2:.4f}, MAE={mae:.0f} USD"
    )

    ARTIFACTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    artifact_path = ARTIFACTS / "model.pkl"

    joblib.dump(
        model,
        artifact_path,
    )

    print(f"[train] artifact persisted: {artifact_path}")

if __name__ == "__main__":
    main()