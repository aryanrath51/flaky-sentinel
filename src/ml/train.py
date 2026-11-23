import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import train_test_split
from src.config import MODEL_PATH, PROCESSED_DATA_DIR, RAW_DATA_DIR
from src.ml.features import FEATURE_COLUMNS, build_feature_dataframe


def _synthetic_bootstrap_df(n_rows: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    rows = []
    for i in range(n_rows):
        is_flake = int(rng.random() < 0.5)
        if is_flake:
            rows.append({
                "duration_seconds": float(rng.uniform(40, 300)),
                "duration_ratio_to_job_avg": float(rng.uniform(1.1, 2.8)),
                "num_touched_files": float(rng.integers(0, 6)),
                "touches_test_file": float(rng.random() < 0.3),
                "touches_doc_or_config_only": float(rng.random() < 0.35),
                "job_hist_fail_rate": float(rng.uniform(0.15, 0.65)),
                "job_recent_flip_count": float(rng.integers(2, 9)),
                "has_timeout_keyword": float(rng.random() < 0.55),
                "has_network_or_registry_keyword": float(rng.random() < 0.45),
                "is_flake": 1,
                "job_name": f"test-suite-{i % 4}",
                "run_id": 1000 + i,
                "head_sha": f"sha{i:04d}",
            })
        else:
            rows.append({
                "duration_seconds": float(rng.uniform(10, 140)),
                "duration_ratio_to_job_avg": float(rng.uniform(0.8, 1.3)),
                "num_touched_files": float(rng.integers(1, 15)),
                "touches_test_file": float(rng.random() < 0.7),
                "touches_doc_or_config_only": 0.0,
                "job_hist_fail_rate": float(rng.uniform(0.0, 0.15)),
                "job_recent_flip_count": float(rng.integers(0, 2)),
                "has_timeout_keyword": float(rng.random() < 0.1),
                "has_network_or_registry_keyword": float(rng.random() < 0.05),
                "is_flake": 0,
                "job_name": f"test-suite-{i % 4}",
                "run_id": 2000 + i,
                "head_sha": f"sha{i:04d}",
            })
    return pd.DataFrame(rows)


def train_model(raw_json_path: Path | None = None) -> dict[str, float]:
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []

    if raw_json_path and raw_json_path.exists():
        records = json.loads(raw_json_path.read_text(encoding="utf-8"))
    else:
        candidates = sorted(RAW_DATA_DIR.glob("*_runs.json"))
        if candidates:
            records = json.loads(candidates[-1].read_text(encoding="utf-8"))

    df = build_feature_dataframe(records)
    if len(df) < 25 or df["is_flake"].nunique() < 2:
        df = _synthetic_bootstrap_df()

    X = df[FEATURE_COLUMNS]
    y = df["is_flake"]

    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    model = LGBMClassifier(
        n_estimators=120,
        learning_rate=0.05,
        num_leaves=15,
        random_state=42,
        verbose=-1,
    )
    model.fit(X_train, y_train)

    val_probs = model.predict_proba(X_val)[:, 1]
    val_preds = (val_probs >= 0.5).astype(int)

    metrics = {
        "train_samples": float(len(X_train)),
        "val_samples": float(len(X_val)),
        "val_accuracy": float(accuracy_score(y_val, val_preds)),
        "val_roc_auc": float(roc_auc_score(y_val, val_probs)),
    }

    joblib.dump({"model": model, "features": FEATURE_COLUMNS, "metrics": metrics}, MODEL_PATH)
    return metrics


if __name__ == "__main__":
    result = train_model()
    print("Training complete:", result)