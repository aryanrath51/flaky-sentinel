from pydantic import BaseModel
from src.agents.quarantine_agent import QuarantineAgent
from src.agents.tools import record_quarantine_event
from src.agents.triage_agent import TriageAgent
from src.config import CIFailureEvent, MLPrediction, QuarantineAction, TriageDecision
from src.ml.predict import FlakinessPredictor


class PipelineReport(BaseModel):
    event: CIFailureEvent
    ml_prediction: MLPrediction
    triage: TriageDecision
    quarantine_action: QuarantineAction
    ledger_path: str


class FlakySentinelPipeline:
    def __init__(self):
        self.predictor = FlakinessPredictor()
        self.triage_agent = TriageAgent()
        self.quarantine_agent = QuarantineAgent()

    def run(self, event: CIFailureEvent) -> PipelineReport:
        is_doc_or_net_flake = (
            all(f.lower().endswith((".md", ".txt", ".rst", ".yml", ".yaml")) for f in event.touched_files)
            or "connectionreseterror" in event.log_tail.lower()
            or "timeout" in event.log_tail.lower()
        )
        hist_rate = 0.35 if is_doc_or_net_flake else 0.05
        flips = 4 if is_doc_or_net_flake else 0

        ml_pred = self.predictor.predict_event(event, hist_fail_rate=hist_rate, flip_count=flips)
        triage = self.triage_agent.triage(event, ml_pred)
        action = self.quarantine_agent.decide_action(event, ml_pred, triage)
        ledger_path = record_quarantine_event(event.run_id, event.head_sha, action)
        return PipelineReport(
            event=event,
            ml_prediction=ml_pred,
            triage=triage,
            quarantine_action=action,
            ledger_path=ledger_path,
        )