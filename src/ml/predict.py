import numpy as np
import pandas as pd
import joblib
from src.config import CIFailureEvent, MODEL_PATH, MLPrediction
from src.ml.features import FEATURE_COLUMNS, build_feature_dataframe
from src.ml.train import train_model


class FlakinessPredictor:
    def __init__(self, model_path=MODEL_PATH):
        if not model_path.exists():
            train_model()
        artifact = joblib.load(model_path)
        self.model = artifact["model"]
        self.features: list[str] = artifact.get("features", FEATURE_COLUMNS)

    def predict_event(self, event: CIFailureEvent, hist_fail_rate: float = 0.15, flip_count: int = 2) -> MLPrediction:
        record = [{
            "repo": event.repo,
            "run_id": event.run_id,
            "head_sha": event.head_sha,
            "created_at": "2026-11-23T00:00:00Z",
            "job_id": event.job_id,
            "job_name": event.job_name,
            "conclusion": "failure",
            "duration_seconds": event.duration_seconds,
            "touched_files": event.touched_files,
            "log_tail": event.log_tail,
        }]
        feat_df = build_feature_dataframe(record)
        if feat_df.empty:
            feat_df = pd.DataFrame([{col: 0.0 for col in self.features}])

        feat_df["job_hist_fail_rate"] = hist_fail_rate
        feat_df["job_recent_flip_count"] = float(flip_count)
        feat_df["duration_ratio_to_job_avg"] = max(1.0, event.duration_seconds / 60.0)

        X = feat_df[self.features]
        flake_prob = float(self.model.predict_proba(X)[:, 1][0])
        flake_prob = float(np.clip(flake_prob, 0.0, 1.0))
        reg_prob = round(1.0 - flake_prob, 4)

        importances = getattr(self.model, "feature_importances_", np.zeros(len(self.features)))
        top_idx = np.argsort(importances)[::-1][:3]
        top_signals = [
            f"{self.features[i]}={round(float(X.iloc[0, i]), 3)}"
            for i in top_idx
        ]

        return MLPrediction(
            flakiness_probability=round(flake_prob, 4),
            regression_probability=reg_prob,
            top_signals=top_signals,
        )