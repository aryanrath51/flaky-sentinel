import json
import time
from typing import Any
import requests
from src.config import RAW_DATA_DIR, settings


class GitHubCIClient:
    BASE_URL = "https://api.github.com"

    def __init__(self, token: str = settings.github_token):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.session = requests.Session()
        self.session.headers.update(headers)

    def _get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        resp = self.session.get(url, params=params, timeout=30)
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            reset = int(resp.headers.get("X-RateLimit-Reset", time.time() + 10))
            sleep_for = max(1, min(reset - int(time.time()) + 1, 30))
            time.sleep(sleep_for)
            resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def fetch_workflow_runs(self, repo: str, per_page: int = 50, pages: int = 2) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        for page in range(1, pages + 1):
            data = self._get(
                f"{self.BASE_URL}/repos/{repo}/actions/runs",
                params={"per_page": per_page, "page": page, "status": "completed"},
            )
            batch = data.get("workflow_runs", [])
            if not batch:
                break
            runs.extend(batch)
        return runs

    def fetch_run_jobs(self, repo: str, run_id: int) -> list[dict[str, Any]]:
        data = self._get(f"{self.BASE_URL}/repos/{repo}/actions/runs/{run_id}/jobs", params={"per_page": 100})
        return data.get("jobs", [])

    def fetch_commit_files(self, repo: str, sha: str) -> list[str]:
        try:
            data = self._get(f"{self.BASE_URL}/repos/{repo}/commits/{sha}")
            return [f.get("filename", "") for f in data.get("files", []) if f.get("filename")]
        except requests.HTTPError:
            return []

    def fetch_job_log_tail(self, repo: str, job_id: int, max_chars: int = 4000) -> str:
        url = f"{self.BASE_URL}/repos/{repo}/actions/jobs/{job_id}/logs"
        resp = self.session.get(url, timeout=30, allow_redirects=True)
        if resp.status_code != 200:
            return f"[Log unavailable: HTTP {resp.status_code}]"
        text = resp.text
        return text[-max_chars:]

    def collect_dataset_snapshot(self, repo: str, max_runs: int = 40) -> list[dict[str, Any]]:
        RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
        runs = self.fetch_workflow_runs(repo, per_page=min(max_runs, 100), pages=1)[:max_runs]
        records: list[dict[str, Any]] = []

        for run in runs:
            run_id = run["id"]
            head_sha = run.get("head_sha", "")
            touched_files = self.fetch_commit_files(repo, head_sha) if head_sha else []
            jobs = self.fetch_run_jobs(repo, run_id)

            for job in jobs:
                conclusion = job.get("conclusion")
                if conclusion not in {"success", "failure"}:
                    continue

                started = job.get("started_at")
                completed = job.get("completed_at")
                duration = 0.0
                if started and completed:
                    from datetime import datetime
                    t0 = datetime.fromisoformat(started.replace("Z", "+00:00"))
                    t1 = datetime.fromisoformat(completed.replace("Z", "+00:00"))
                    duration = max(0.0, (t1 - t0).total_seconds())

                log_tail = ""
                if conclusion == "failure":
                    log_tail = self.fetch_job_log_tail(repo, job["id"])

                records.append({
                    "repo": repo,
                    "run_id": run_id,
                    "run_attempt": run.get("run_attempt", 1),
                    "head_sha": head_sha,
                    "created_at": run.get("created_at"),
                    "job_id": job["id"],
                    "job_name": job.get("name", "unknown"),
                    "conclusion": conclusion,
                    "duration_seconds": duration,
                    "touched_files": touched_files,
                    "log_tail": log_tail,
                })

        out_path = RAW_DATA_DIR / f"{repo.replace('/', '_')}_runs.json"
        out_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
        return records