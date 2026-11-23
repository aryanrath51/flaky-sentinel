import numpy as np
import pandas as pd
import joblib
import json
from src.config import CIFailureEvent, MODEL_PATH, MLPrediction
from src.ml.features import FEATURE_COLUMNS, build_feature_dataframe
from src.ml.train import train_model
from src.config import CIFailureEvent
from datetime import datetime, timezone
from src.config import PROCESSED_DATA_DIR, QuarantineAction


def record_quarantine_event(run_id: int, head_sha: str, action: QuarantineAction) -> str:
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    ledger_path = PROCESSED_DATA_DIR / "quarantine_ledger.json"
    entries: list[dict] = []
    if ledger_path.exists():
        entries = json.loads(ledger_path.read_text(encoding="utf-8"))

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "head_sha": head_sha,
        "action": action.action,
        "target_job": action.target_job,
        "rationale": action.rationale,
    }
    entries.append(entry)
    ledger_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    return str(ledger_path)


def extract_error_lines(log_tail: str, max_lines: int = 25) -> str:
    lines = [ln.strip() for ln in log_tail.splitlines() if ln.strip()]
    highlighted = [
        ln for ln in lines
        if any(tok in ln.lower() for tok in ("error", "fail", "exception", "timeout", "assert", "traceback"))
    ]
    selected = highlighted[-max_lines:] if highlighted else lines[-max_lines:]
    return "\n".join(selected) if selected else "[No error lines found in log tail]"


def summarize_touched_files(event: CIFailureEvent) -> str:
    if not event.touched_files:
        return "No commit file list available."
    preview = ", ".join(event.touched_files[:15])
    extra = f" (+{len(event.touched_files) - 15} more)" if len(event.touched_files) > 15 else ""
    return f"{len(event.touched_files)} file(s) touched: {preview}{extra}"


def build_bisect_plan(base_sha: str | None, head_sha: str, job_name: str) -> list[str]:
    start = base_sha or "HEAD~10"
    return [
        f"git bisect start {head_sha} {start}",
        f"Run isolated check for job '{job_name}' at each step",
        "git bisect reset after identifying first bad commit",
    ]


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