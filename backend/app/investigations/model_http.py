import json
import time

import httpx2

from .control import ModelLimit


def request_json(settings, payload, transport=None, *, budget=None, purpose="explainer"):
    deadline = time.monotonic() + settings.model_timeout_seconds
    if budget:
        deadline = min(deadline, budget.deadline)
    if deadline <= time.monotonic():
        if budget:
            budget.limit("runtime_limit")
        raise ModelLimit("runtime_limit")
    call_id = budget.reserve(payload, purpose) if budget else None
    try:
        if time.monotonic() >= deadline:
            raise ModelLimit("runtime_limit")
        with httpx2.Client(trust_env=False, follow_redirects=False, transport=transport) as client:
            with client.stream(
                "POST",
                settings.model_endpoint,
                json=payload,
                timeout=max(0.001, deadline - time.monotonic()),
                headers={
                    "Authorization": f"Bearer {settings.ai_provider_api_key.get_secret_value()}",
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                },
            ) as response:
                if (
                    response.status_code != 200
                    or "application/json" not in response.headers.get("content-type", "")
                    or response.headers.get("content-encoding", "identity") != "identity"
                ):
                    raise ModelLimit("model_unavailable")
                content = bytearray()
                for chunk in response.iter_raw(chunk_size=8192):
                    content.extend(chunk)
                    if len(content) > 65536:
                        raise ModelLimit("response_limit")
                    if time.monotonic() >= deadline:
                        raise ModelLimit("runtime_limit")
                result = json.loads(content)
        if budget:
            budget.finish(call_id, "succeeded")
        return result
    except (ModelLimit, httpx2.HTTPError, ValueError, UnicodeError) as failure:
        if budget:
            code = failure.code if isinstance(failure, ModelLimit) else "model_unavailable"
            if code == "runtime_limit":
                budget.stop_reason = code
            budget.finish(call_id, "failed", code)
        raise
