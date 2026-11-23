import argparse
import json
from src.collectors.github_ci import GitHubCIClient
from src.config import CIFailureEvent, PROCESSED_DATA_DIR, RAW_DATA_DIR, settings
from src.ml.train import train_model
from src.pipeline import FlakySentinelPipeline


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
    print(report.model_dump_json(indent=2))


def run_latest_failed_job(repo: str) -> None:
    raw_path = RAW_DATA_DIR / f"{repo.replace('/', '_')}_runs.json"
    if not raw_path.exists():
        print(f"No collected data at {raw_path}. Run `collect --repo {repo}` first.")
        return

    records = json.loads(raw_path.read_text(encoding="utf-8"))
    failures = [r for r in records if r.get("conclusion") == "failure"]
    if not failures:
        print(f"No failed jobs found in {raw_path.name}.")
        return

    latest = failures[-1]
    event = CIFailureEvent(
        repo=latest.get("repo", repo),
        run_id=int(latest["run_id"]),
        job_id=int(latest["job_id"]),
        job_name=latest.get("job_name", "unknown-job"),
        head_sha=latest.get("head_sha", ""),
        duration_seconds=float(latest.get("duration_seconds", 0.0)),
        touched_files=latest.get("touched_files", []),
        log_tail=latest.get("log_tail", ""),
    )
    report = FlakySentinelPipeline().run(event)
    print(report.model_dump_json(indent=2))


def show_ledger() -> None:
    ledger_path = PROCESSED_DATA_DIR / "quarantine_ledger.json"
    if not ledger_path.exists():
        print("Quarantine ledger is empty (no entries yet).")
        return
    entries = json.loads(ledger_path.read_text(encoding="utf-8"))
    print(json.dumps(entries, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Flaky Sentinel CLI")
    parser.add_argument(
        "command",
        choices=["collect", "train", "sample", "regression", "triage-latest", "ledger"],
        default="sample",
        nargs="?",
    )
    parser.add_argument("--repo", default=settings.target_repo)
    parser.add_argument("--max-runs", type=int, default=30)
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
    elif args.command == "triage-latest":
        run_latest_failed_job(args.repo)
    elif args.command == "ledger":
        show_ledger()
    else:
        run_sample()


if __name__ == "__main__":
    main()