# Flaky Sentinel

A hybrid **Machine Learning + AI Agent** CI/CD failure triage and quarantine pipeline built with Python, **LightGBM**, **Google GenAI (`google-genai`)**, and **Flask**.

Instead of treating every failed CI job as a code regression, **Flaky Sentinel** combines historical build/Git signals in a tabular ML model with structured LLM triage and quarantine agents to distinguish intermittent flakes and environment/dependency issues from real regressions.

## Key Features
- **GitHub CI Data Collector (`src/collectors/github_ci.py`)**: Pulls completed GitHub Actions workflow runs, job execution durations, commit file lists, and failure log tails via the GitHub REST API.
- **ML Risk Model (`src/ml/`)**: Extracts leakage-safe historical job failure/flip rates, run-duration ratios, commit file indicators (`tests`, docs/configs, file counts), and log error keywords to score `flakiness_probability` vs. `regression_probability` using `LightGBM`.
- **Multi-Agent Triage & Quarantine (`src/agents/`, `src/pipeline.py`)**:
  - **Triage Agent**: Classifies failures into `likely_flake`, `real_regression`, or `env_dependency_issue` using typed Pydantic schemas (`TriageDecision`) with automatic model fallback.
  - **Quarantine Agent**: Selects an action (`rerun_and_quarantine`, `retry_env_runner`, `bisect_and_block`, or `manual_review`), generates `git bisect` steps for regressions, and appends decisions to `data/processed/quarantine_ledger.json`.
- **Dark-Mode Web Console (`src/web.py`)**: Local Flask interface to trigger flake or regression scenarios, inspect ML probabilities and agent reasoning, and review the quarantine ledger.
- **Unit Tests (`tests/test_features.py`)**: Validates feature extraction and probability bounds with `pytest`.

## Project Structure

```text
flaky-sentinel/
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
├── .github/
│   └── workflows/
│       └── flaky-sentinel.yml
├── data/
│   ├── raw/                  # Raw GitHub Actions snapshots (gitignored)
│   └── processed/            # Trained LightGBM artifact & quarantine ledger
├── src/
│   ├── config.py             # Environment settings & Pydantic schemas
│   ├── collectors/
│   │   └── github_ci.py      # GitHub Actions REST API collector
│   ├── ml/
│   │   ├── features.py       # Feature engineering & weak-supervision labels
│   │   ├── train.py          # LightGBM training & evaluation
│   │   └── predict.py        # Model inference & top signal extraction
│   ├── agents/
│   │   ├── tools.py          # Log filtering, file summary, bisect & ledger helpers
│   │   ├── triage_agent.py   # Gemini Triage Agent
│   │   └── quarantine_agent.py # Gemini Quarantine & Bisect Agent
│   ├── pipeline.py           # End-to-end ML + Agent orchestrator
│   ├── main.py               # CLI entry point
│   └── web.py                # Flask dark-mode dashboard
└── tests/
    └── test_features.py      # Pytest unit tests