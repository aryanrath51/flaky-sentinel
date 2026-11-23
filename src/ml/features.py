import re
from typing import Any
import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "duration_seconds",
    "duration_ratio_to_job_avg",
    "num_touched_files",
    "touches_test_file",
    "touches_doc_or_config_only",
    "job_hist_fail_rate",
    "job_recent_flip_count",
    "has_timeout_keyword",
    "has_network_or_registry_keyword",
]

TIMEOUT_RE = re.compile(r"(timeout|timed out|deadline exceeded|etimedout)", re.IGNORECASE)
NET_ENV_RE = re.compile(
    r"(econnreset|enotfound|502 bad gateway|503 service unavailable|rate limit|npm err!|pip.*connection)",
    re.IGNORECASE,
)


def _is_test_file(path: str) -> bool:
    p = path.lower()
    return "test" in p or "spec" in p or "__tests__" in p


def _is_doc_or_config(path: str) -> bool:
    p = path.lower()
    return p.endswith((".md", ".txt", ".rst", ".yml", ".yaml", ".json", ".toml", ".cfg"))


def build_feature_dataframe(records: list[dict[str, Any]]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=FEATURE_COLUMNS + ["is_flake", "job_name", "run_id", "head_sha"])

    df = pd.DataFrame(records).copy()
    df["created_dt"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True)
    df = df.sort_values(["job_name", "created_dt", "run_id"]).reset_index(drop=True)

    df["is_failed"] = (df["conclusion"] == "failure").astype(int)
    df["duration_seconds"] = pd.to_numeric(df["duration_seconds"], errors="coerce").fillna(0.0)

    # Historical job duration & failure rate using expanding prior history (avoids target leakage)
    job_avg_dur = (
        df.groupby("job_name")["duration_seconds"]
        .transform(lambda s: s.shift(1).expanding().mean())
        .fillna(df["duration_seconds"].replace(0, np.nan).mean())
        .fillna(1.0)
    )
    df["duration_ratio_to_job_avg"] = np.where(
        job_avg_dur > 0, df["duration_seconds"] / job_avg_dur, 1.0
    )

    df["job_hist_fail_rate"] = (
        df.groupby("job_name")["is_failed"]
        .transform(lambda s: s.shift(1).expanding().mean())
        .fillna(0.1)
    )

    # Count conclusion flips (success <-> failure) in prior runs of the same job
    def _prior_flips(series: pd.Series) -> pd.Series:
        shifted = series.shift(1)
        flips = (shifted != shifted.shift(1)).astype(int)
        flips.iloc[0] = 0
        return flips.cumsum()

    df["job_recent_flip_count"] = df.groupby("job_name")["is_failed"].transform(_prior_flips)

    touched_lists = df["touched_files"].apply(lambda x: x if isinstance(x, list) else [])
    df["num_touched_files"] = touched_lists.apply(len).astype(float)
    df["touches_test_file"] = touched_lists.apply(
        lambda files: float(any(_is_test_file(f) for f in files))
    )
    df["touches_doc_or_config_only"] = touched_lists.apply(
        lambda files: float(len(files) > 0 and all(_is_doc_or_config(f) for f in files))
    )

    logs = df["log_tail"].fillna("").astype(str)
    df["has_timeout_keyword"] = logs.apply(lambda t: float(bool(TIMEOUT_RE.search(t))))
    df["has_network_or_registry_keyword"] = logs.apply(lambda t: float(bool(NET_ENV_RE.search(t))))

    # Weak-supervision label for failed runs: high historical flip/flake signal + low code-change signal
    flake_score = (
        0.45 * df["job_hist_fail_rate"].clip(0, 1)
        + 0.25 * (df["job_recent_flip_count"].clip(0, 5) / 5.0)
        + 0.20 * np.maximum(df["has_timeout_keyword"], df["has_network_or_registry_keyword"])
        + 0.10 * df["touches_doc_or_config_only"]
        - 0.25 * (1.0 - df["touches_doc_or_config_only"]) * (df["num_touched_files"].clip(0, 10) / 10.0)
    )
    df["is_flake"] = (flake_score >= 0.35).astype(int)

    failed_df = df[df["is_failed"] == 1].copy()
    return failed_df[FEATURE_COLUMNS + ["is_flake", "job_name", "run_id", "head_sha"]].reset_index(drop=True)