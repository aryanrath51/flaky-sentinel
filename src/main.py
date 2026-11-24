import argparse
import json
from pathlib import Path
from src.collectors.github_ci import GitHubCIClient
from src.config import CIFailureEvent, PROCESSED_DATA_DIR, RAW_DATA_DIR, settings
from src.ml.train import train_model
from src.pipeline import FlakySentinelPipeline, PipelineReport


def format_pr_markdown(report: PipelineReport) -> str:
    ev = report.event
    ml = report.ml_prediction
    tr = report.triage
    qa = report.quarantine_action

    badge = "⚠️ Likely Flake" if tr.category == "likely_flake" else (
        "🛑 Real Regression" if tr.category == "real_regression" else "🔧 Env / Dependency Issue"
    )
    evidence_md = "\n".join(f"- {item}" for item in tr.evidence) or "- None"
    steps_md = "\n".join(f"{i}. {step}" for i, step in enumerate(qa.next_steps, 1)) or "1. Review logs"

    return f"""## 🛡️ Flaky Sentinel CI Triage Report

**Verdict:** {badge} (`{tr.category}`, confidence: `{tr.confidence:.2%}`)  
**Target Job:** `{ev.job_name}` (Run `#{ev.run_id}`, Commit `{ev.head_sha[:7]}`)  
**Recommended Quarantine Action:** `{qa.action}`

### 📊 ML Risk Signals (LightGBM)
| Metric | Score |
| :--- | :--- |
| **Flakiness Probability** | `{ml.flakiness_probability:.2%}` |
| **Regression Probability** | `{ml.regression_probability:.2%}` |

**Top Features:** `{"`, `".join(ml.top_signals)}`

### 🧠 Agent Triage Reasoning
{tr.reasoning}

**Evidence:**
{evidence_md}

### 🔒 Quarantine & Next Steps
{qa.rationale}

{steps_md}
"""


def save_pr_comment_artifact(report: PipelineReport) -> Path:
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DATA_DIR / "pr_comment.md"
    out_path.write_text(format_pr_markdown(report), encoding="utf-8")
    return out_path


def run_sample() -> None:
    sample_event = CIFailureEvent(
        repo=settings.target_repo,
        run_id=9001,
        job_id=4201,
        job_name="integration-tests",
        head_sha="8f3a1b2",
        base_sha="7c2d09e",
        duration_seconds=245.0,
        touched_files=["README.md", "docs/setup.md"],
        log_tail="2026-11-23T10:00:01Z ERROR: ConnectionResetError: [Errno 104] Connection reset by peer during webhook callback",
    )
    report = FlakySentinelPipeline().run(sample_event)
    save_pr_comment_artifact(report)
    print(report.model_dump_json(indent=2))


def run_regression() -> None:
    regression_event = CIFailureEvent(
        repo=settings.target_repo,
        run_id=9002,
        job_id=4202,
        job_name="unit-tests",
        head_sha="9d4e2c1",
        base_sha="8f3a1b2",
        duration_seconds=58.0,
        touched_files=["src/flask/app.py", "src/flask/ctx.py", "tests/test_appctx.py"],
        log_tail=(
            "FAILED tests/test_appctx.py::test_app_context_teardown - AssertionError: "
            "assert teardown_called == [True] where teardown_called = []"
        ),
    )
    report = FlakySentinelPipeline().run(regression_event)
    save_pr_comment_artifact(report)
    print(report.model_dump_json(indent=2))


def run_live_github_run(repo: str, run_id: int) -> None:
    client = GitHubCIClient()
    runs_data = client.get_json(f"/repos/{repo}/actions/runs/{run_id}")
    jobs_data = client.get_json(f"/repos/{repo}/actions/runs/{run_id}/jobs").get("jobs", [])
    failed_jobs = [j for j in jobs_data if j.get("conclusion") == "failure"]

    if not failed_jobs:
        print(f"No failed jobs found in run {run_id}.")
        return

    job = failed_jobs[0]
    head_sha = runs_data.get("head_sha", "")
    touched_files = client.fetch_commit_files(repo, head_sha) if head_sha else []
    log_tail = client.fetch_job_log_tail(repo, int(job["id"]))

    event = CIFailureEvent(
        repo=repo,
        run_id=run_id,
        job_id=int(job["id"]),
        job_name=job.get("name", "ci-job"),
        head_sha=head_sha,
        duration_seconds=60.0,
        touched_files=touched_files,
        log_tail=log_tail,
    )
    report = FlakySentinelPipeline().run(event)
    md_path = save_pr_comment_artifact(report)
    print(f"Saved PR triage comment to {md_path}")
    print(report.model_dump_json(indent=2))


def show_ledger() -> None:
    ledger_path = PROCESSED_DATA_DIR / "quarantine_ledger.json"
    if not ledger_path.exists():
        print("Quarantine ledger is empty (no entries yet).")
        return
    print(ledger_path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Flaky Sentinel CLI")
    parser.add_argument(
        "command",
        choices=["collect", "train", "sample", "regression", "triage-run", "ledger"],
        default="sample",
        nargs="?",
    )
    parser.add_argument("--repo", default=settings.target_repo)
    parser.add_argument("--max-runs", type=int, default=30)
    parser.add_argument("--run-id", type=int, default=0)
    args = parser.parse_args()

    if args.command == "collect":
        client = GitHubCIClient()
        rows = client.collect_dataset_snapshot(args.repo, max_runs=args.max_runs)
        print(f"Collected {len(rows)} job records for {args.repo}")
    elif args.command == "train":
        metrics = train_model()
        print("Model trained:", metrics)
    elif args.command == "regression":
        run_regression()
    elif args.command == "triage-run":
        if not args.run_id:
            raise ValueError("--run-id is required for triage-run")
        run_live_github_run(args.repo, args.run_id)
    elif args.command == "ledger":
        show_ledger()
    else:
        run_sample()


if __name__ == "__main__":
    main()