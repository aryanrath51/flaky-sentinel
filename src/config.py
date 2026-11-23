import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DATA_DIR = BASE_DIR / "data" / "processed"
MODEL_PATH = PROCESSED_DATA_DIR / "flakiness_lgbm.joblib"


class Settings(BaseModel):
    github_token: str = Field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))
    gemini_api_key: str = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_model: str = Field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"))
    target_repo: str = Field(default_factory=lambda: os.getenv("TARGET_REPO", "pallets/flask"))
    flake_confidence_threshold: float = 0.75


class CIFailureEvent(BaseModel):
    repo: str
    run_id: int
    job_id: int
    job_name: str
    head_sha: str
    base_sha: str | None = None
    duration_seconds: float
    log_tail: str
    touched_files: list[str] = Field(default_factory=list)


class MLPrediction(BaseModel):
    flakiness_probability: float = Field(ge=0.0, le=1.0)
    regression_probability: float = Field(ge=0.0, le=1.0)
    top_signals: list[str] = Field(default_factory=list)


class TriageDecision(BaseModel):
    category: str  # "likely_flake" | "real_regression" | "env_dependency_issue"
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    evidence: list[str] = Field(default_factory=list)


class QuarantineAction(BaseModel):
    action: str  # "rerun_and_quarantine" | "bisect_and_block" | "retry_env_runner" | "manual_review"
    target_job: str
    rationale: str
    next_steps: list[str] = Field(default_factory=list)


settings = Settings()