import hashlib
import json
from decimal import Decimal

import pytest

from app.schemas.schemas import AIAnalysisResult
from scripts.terra_text_smoke import (
    SMOKE_ID,
    SmokeAuthorizationError,
    build_smoke_descriptor,
    build_smoke_request_bytes,
    claim_smoke_attempt,
    run_authorized_smoke,
    validate_authorization,
)


HEAD = "a" * 40


def _authorization(descriptor):
    return {
        **descriptor,
        "authorization_scope": "production_text_smoke",
        "authorized": True,
    }


def test_descriptor_binds_actual_production_request_and_small_cost_ceiling():
    descriptor = build_smoke_descriptor(HEAD)

    assert descriptor["smoke_id"] == SMOKE_ID
    assert descriptor["repository_head"] == HEAD
    assert descriptor["provider"] == "OpenAI"
    assert descriptor["model"] == "gpt-5.6-terra"
    assert descriptor["endpoint"] == "https://api.openai.com/v1/responses"
    assert descriptor["maximum_physical_attempts"] == 1
    assert descriptor["retries"] == 0
    assert descriptor["timeout_seconds"] == 30
    assert descriptor["maximum_output_tokens"] == 2048
    assert descriptor["store"] is False
    assert descriptor["stream"] is False
    assert descriptor["tools_enabled"] is False
    assert descriptor["fixture_id"] == "terra-production-text-smoke-synthetic-v1"
    assert descriptor["prompt_version"] == "v4"
    assert Decimal(descriptor["cost_ceiling_usd"]) < Decimal("0.05")

    request_bytes = build_smoke_request_bytes()
    assert hashlib.sha256(request_bytes).hexdigest() == descriptor["request_hash"]
    request = json.loads(request_bytes)
    assert request["model"] == descriptor["model"]
    assert request["max_output_tokens"] == descriptor["maximum_output_tokens"]
    assert "tools" not in request


def test_authorization_requires_an_exact_closed_identity():
    descriptor = build_smoke_descriptor(HEAD)
    authorization = _authorization(descriptor)

    validate_authorization(authorization, descriptor)

    for mutation in (
        lambda value: value.__setitem__("request_hash", "0" * 64),
        lambda value: value.__setitem__("maximum_physical_attempts", 2),
        lambda value: value.__setitem__("retries", 1),
        lambda value: value.__setitem__("unexpected", True),
        lambda value: value.__setitem__("authorized", False),
    ):
        changed = dict(authorization)
        mutation(changed)
        with pytest.raises(SmokeAuthorizationError):
            validate_authorization(changed, descriptor)


def test_authorized_smoke_uses_production_adapter_once_with_retries_disabled():
    descriptor = build_smoke_descriptor(HEAD)
    observed = {"factory_calls": 0, "analyze_calls": 0}

    class FakeProvider:
        def __init__(self, *, maximum_attempts):
            observed["factory_calls"] += 1
            observed["maximum_attempts"] = maximum_attempts
            self.model_name = "gpt-5.6-terra"

        def request_payload(self, listing):
            from app.services.ai import build_openai_responses_payload

            return build_openai_responses_payload(listing, self.model_name)

        def analyze(self, listing):
            observed["analyze_calls"] += 1
            result = AIAnalysisResult(
                summary="No obvious risk indicators were found.",
                risk_level="low",
                risk_indicators=[],
                price_assessment="Current pricing was not verified.",
                price_plausibility="plausible",
                seller_questions=["Can I inspect the item before paying?"],
                recommendation="buy",
            )
            return result, result.model_dump_json()

    record = run_authorized_smoke(
        _authorization(descriptor),
        repository_head=HEAD,
        provider_factory=FakeProvider,
    )

    assert observed == {
        "factory_calls": 1,
        "maximum_attempts": 1,
        "analyze_calls": 1,
    }
    assert record["smoke_id"] == SMOKE_ID
    assert record["result_status"] == "accepted"
    assert record["physical_attempts"] == 1
    assert record["retries"] == 0
    assert record["raw_response_retained"] is False
    assert record["provider_response_hash"]


def test_smoke_stops_before_provider_construction_on_head_mismatch():
    descriptor = build_smoke_descriptor(HEAD)
    calls = 0

    def provider_factory(**kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("provider must not be constructed")

    with pytest.raises(SmokeAuthorizationError):
        run_authorized_smoke(
            _authorization(descriptor),
            repository_head="b" * 40,
            provider_factory=provider_factory,
        )

    assert calls == 0


def test_attempt_claim_is_atomic_and_single_use(tmp_path):
    descriptor = build_smoke_descriptor(HEAD)

    claim_smoke_attempt(tmp_path, descriptor)

    marker = json.loads((tmp_path / "attempt-started.json").read_text())
    assert marker == {
        "smoke_id": SMOKE_ID,
        "repository_head": HEAD,
        "request_hash": descriptor["request_hash"],
        "maximum_physical_attempts": 1,
        "retries": 0,
    }
    with pytest.raises(SmokeAuthorizationError):
        claim_smoke_attempt(tmp_path, descriptor)
