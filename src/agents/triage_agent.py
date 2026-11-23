from google import genai
from google.genai import types
from google.genai.errors import ServerError, ClientError
from src.agents.tools import extract_error_lines, summarize_touched_files
from src.config import CIFailureEvent, MLPrediction, TriageDecision, settings


class TriageAgent:
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

    def _deterministic_fallback(self, event: CIFailureEvent, ml_pred: MLPrediction, reason: str) -> TriageDecision:
        file_summary = summarize_touched_files(event)
        category = (
            "likely_flake"
            if ml_pred.flakiness_probability >= settings.flake_confidence_threshold
            else "real_regression"
        )
        return TriageDecision(
            category=category,
            confidence=ml_pred.flakiness_probability if category == "likely_flake" else ml_pred.regression_probability,
            reasoning=reason,
            evidence=[file_summary, f"ML signals: {', '.join(ml_pred.top_signals)}"],
        )

    def triage(self, event: CIFailureEvent, ml_pred: MLPrediction) -> TriageDecision:
        error_excerpt = extract_error_lines(event.log_tail)
        file_summary = summarize_touched_files(event)

        if not self.client:
            return self._deterministic_fallback(event, ml_pred, "Fallback deterministic triage (GEMINI_API_KEY not set).")

        prompt = f"""
You are a senior CI/CD Triage Agent. Classify this failed job into EXACTLY one category:
- "likely_flake": intermittent timing, race condition, transient network/runner hiccup, or unrelated commit.
- "real_regression": failure directly caused by code/config changes in this commit or test assertion failure in touched logic.
- "env_dependency_issue": broken external package registry, missing runner tool, expired credential, or infrastructure outage.

Repository: {event.repo}
Job Name: {event.job_name}
Duration (s): {event.duration_seconds}
Commit SHA: {event.head_sha} (Base: {event.base_sha or "unknown"})
Touched Files: {file_summary}

ML Model Output:
- Flakiness probability: {ml_pred.flakiness_probability}
- Regression probability: {ml_pred.regression_probability}
- Top signals: {", ".join(ml_pred.top_signals)}

Error Log Excerpt:
{error_excerpt}
"""

        last_err: Exception | None = None
        for model_name in self._fallback_models():
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=TriageDecision,
                        temperature=0.1,
                    ),
                )
                return TriageDecision.model_validate_json(response.text)
            except ServerError as exc:
                last_err = exc
                continue
            except ClientError as exc:
                if exc.code in (404, 429):
                    last_err = exc
                    continue
                raise

        return self._deterministic_fallback(
            event,
            ml_pred,
            f"All Gemini models busy/unavailable ({last_err}); used deterministic ML fallback.",
        )