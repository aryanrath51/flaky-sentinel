from src.config import CIFailureEvent, MLPrediction, TriageDecision
from src.ml.features import FEATURE_COLUMNS, build_feature_dataframe
from src.ml.predict import FlakinessPredictor


def test_build_feature_dataframe_filters_failed_jobs():
    records = [
        {
            "repo": "pallets/flask",
            "run_id": 1,
            "head_sha": "aaa111",
            "created_at": "2026-11-20T10:00:00Z",
            "job_id": 10,
            "job_name": "tests",
            "conclusion": "success",
            "duration_seconds": 60.0,
            "touched_files": ["src/flask/app.py"],
            "log_tail": "",
        },
        {
            "repo": "pallets/flask",
            "run_id": 2,
            "head_sha": "bbb222",
            "created_at": "2026-11-20T11:00:00Z",
            "job_id": 11,
            "job_name": "tests",
            "conclusion": "failure",
            "duration_seconds": 180.0,
            "touched_files": ["README.md"],
            "log_tail": "ERROR: ConnectionResetError: timed out",
        },
    ]
    df = build_feature_dataframe(records)
    assert len(df) == 1
    for col in FEATURE_COLUMNS:
        assert col in df.columns


def test_predictor_returns_valid_probabilities():
    predictor = FlakinessPredictor()
    event = CIFailureEvent(
        repo="pallets/flask",
        run_id=500,
        job_id=900,
        job_name="tests",
        head_sha="ccc333",
        duration_seconds=90.0,
        touched_files=["README.md"],
        log_tail="TimeoutError after 30s",
    )
    pred: MLPrediction = predictor.predict_event(event, hist_fail_rate=0.4, flip_count=4)
    assert 0.0 <= pred.flakiness_probability <= 1.0
    assert 0.0 <= pred.regression_probability <= 1.0
    assert abs((pred.flakiness_probability + pred.regression_probability) - 1.0) < 1e-3