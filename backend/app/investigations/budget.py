import json
import time
from decimal import ROUND_UP, Decimal
from uuid import uuid4

from ..models import Investigation, ModelCall
from .control import ModelLimit, WorkStopped


class ModelBudget:
    """Reserve before sending; never refund ambiguous failures or worker crashes."""

    def __init__(self, worker, claim):
        self.worker, self.claim, self.settings = worker, claim, worker.settings
        self.deadline = time.monotonic() + self.settings.investigation_max_seconds
        self.stop_reason = None
        self.last_call_id = None

    def limit(self, code):
        self.stop_reason = code
        raise ModelLimit(code)

    def reserve(self, payload, purpose):
        settings = self.settings
        if time.monotonic() >= self.deadline:
            self.limit("runtime_limit")
        if (
            settings.model_input_usd_per_million is None
            or settings.model_output_usd_per_million is None
        ):
            self.limit("budget_not_configured")
        # Conservative byte-based estimate, plus protocol overhead. Not a billing quote.
        input_tokens = len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) + 1024
        completion_tokens = payload["max_completion_tokens"]
        if input_tokens > settings.model_max_input_token_estimate:
            self.limit("context_limit")
        cost = (
            (
                Decimal(input_tokens) * settings.model_input_usd_per_million
                + Decimal(completion_tokens) * settings.model_output_usd_per_million
            )
            / Decimal(1_000_000)
        ).quantize(Decimal("0.000001"), rounding=ROUND_UP)
        with self.worker.session_factory() as session:
            job = self.worker.owned_job(session, self.claim)
            if job is None:
                raise WorkStopped("superseded")
            investigation = session.get(Investigation, self.claim.investigation_id)
            if not self.worker.eligible(session, investigation, lock=True):
                self.worker.fail(job, investigation)
                session.commit()
                raise WorkStopped("failed")
            if (
                job.model_call_count >= settings.model_max_calls
                or job.reserved_model_cost_usd + cost > settings.model_budget_usd
            ):
                self.limit("budget_limit")
            job.model_call_count += 1
            job.reserved_model_cost_usd += cost
            call = ModelCall(
                id=uuid4(),
                workspace_id=self.claim.workspace_id,
                investigation_id=self.claim.investigation_id,
                job_id=self.claim.job_id,
                attempt=self.claim.attempt,
                sequence=job.model_call_count,
                purpose=purpose,
                state="reserved",
                input_token_estimate=input_tokens,
                max_completion_tokens=completion_tokens,
                reserved_cost_usd=cost,
            )
            session.add(call)
            session.commit()
            self.last_call_id = call.id
            return call.id

    def finish(self, call_id, state, code=None):
        with self.worker.session_factory() as session:
            call = session.get(ModelCall, call_id)
            if call and call.job_id == self.claim.job_id:
                call.state, call.error_code = state, code
                session.commit()
