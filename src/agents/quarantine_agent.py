from google import genai
from google.genai import types
from google.genai.errors import ServerError, ClientError
from src.agents.tools import build_bisect_plan
from src.config import CIFailureEvent, MLPrediction, QuarantineAction, TriageDecision, settings


class QuarantineAgent:
    def __init__(self):
        self.client = genai.Client(api_key=settings.gemini_api_key) if settings.gemini_api_key else None
        self.model = settings.gemini_model

    def _fallback_models(self) -> list[str]:
        candidates = [
            self.model,
            "gemini-3.8-flash",
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash-lite",
        ]
        seen: list[str] = []
        for m in candidates:
            clean = m.removeprefix("models/")
            if clean and clean not in seen:
                seen.append(clean)
        return seen

    def _deterministic_action(self, event: CIFailureEvent, triage: TriageDecision, bisect_steps: list[str], reason: str) -> QuarantineAction:
        if triage.category == "likely_flake":
            return QuarantineAction(
                action="rerun_and_quarantine",
                target_job=event.job_name,
                rationale=reason,
                next_steps=[f"Trigger isolated re-run for job '{event.job_name}'", "Record flake occurrence in quarantine ledger"],
            )
        if triage.category == "env_dependency_issue":
            return QuarantineAction(
                action="retry_env_runner",
                target_job=event.job_name,
                rationale=reason,
                next_steps=["Clear runner/dependency cache if needed", f"Re-run '{event.job_name}'"],
            )
        return QuarantineAction(
            action="bisect_and_block",
            target_job=event.job_name,
            rationale=reason,
            next_steps=bisect_steps,
        )

    def decide_action(
        self,
        event: CIFailureEvent,
        ml_pred: MLPrediction,
        triage: TriageDecision,
    ) -> QuarantineAction:
        bisect_steps = build_bisect_plan(event.base_sha, event.head_sha, event.job_name)

        if not self.client:
            return self._deterministic_action(event, triage, bisect_steps, "Fallback rule action (GEMINI_API_KEY not set).")

        prompt = f"""
You are a senior Release Quarantine & Bisect Agent. Choose the safest automated action:
- "rerun_and_quarantine"
- "bisect_and_block"
- "retry_env_runner"
- "manual_review"

Job: {event.job_name} (Run #{event.run_id}, SHA {event.head_sha})
ML Flakiness Prob: {ml_pred.flakiness_probability} | Regression Prob: {ml_pred.regression_probability}
Triage Category: {triage.category} (Confidence: {triage.confidence})
Triage Reasoning: {triage.reasoning}
Suggested Bisect Commands if regressing: {bisect_steps}
"""

        last_err: Exception | None = None
        for model_name in self._fallback_models():
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=QuarantineAction,
                        temperature=0.1,
                    ),
                )
                return QuarantineAction.model_validate_json(response.text)
            except ServerError as exc:
                last_err = exc
                continue
            except ClientError as exc:
                if exc.code in (404, 429):
                    last_err = exc
                    continue
                raise

        return self._deterministic_action(
            event,
            triage,
            bisect_steps,
            f"All Gemini models busy/unavailable ({last_err}); used deterministic quarantine rule.",
        )