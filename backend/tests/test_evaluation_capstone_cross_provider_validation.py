"""Provider-free tests for the minimal cross-provider Capstone text validation."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import stat
import subprocess

import pytest

from app.services.evaluation_capstone_live_validation import (
    CapstoneLiveValidationError,
)
from app.services.evaluation_live_transport import (
    ConcreteLivePilotTransport,
    HttpResponse,
    LazyEnvironmentCredentialResolver,
)
from app.services.evaluation_pilot_runner import _synthetic_provider_envelope
from tests.test_evaluation_capstone_live_validation import (
    _V1_RESERVATION,
    _V1_RESULT,
)


ROOT = Path(__file__).resolve().parents[2]
HEAD = subprocess.run(
    ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()
SOL_CASE_ID = "capval-openai-sol-pt1-v1"
GEMINI_CASE_ID = "capval-gemini-flash-pt1-v1"
CANARY = "cross-provider-test-canary-not-a-real-secret"
RUNTIME_IDENTITY = {
    "python_executable": "/test/python",
    "python_implementation": "CPython",
    "python_version": "3.12.13",
    "http_client_package": "httpx",
    "http_client_version": "0.28.1",
    "http_client_requirement": "httpx>=0.27",
}
_V2_RESERVATION = json.loads(
    r'''{"authorization_hash":"9a84b4b07b81b503376a23cccdc0b953963fe4299b5f705279c348f173f9c277","conservative_reservation_usd":"0.05169700","contract_hash":"48831c6dfafcdd00ab7e8a525d448574526ffefbfbf9c6d1bf9c105299af13be","cumulative_worst_case_validation_exposure_usd":"0.10339400","execution_class":"capstone_live_validation","predecessor_reservation_record_hash":"a9d604c30f16ecd4525d533955f9701ea15ed78c35cb7fff703c3e3761cd1bab","predecessor_result_record_hash":"554fdf1685a4b766698d9af255fd7921e3500a7390915957831eab440582d24e","predecessor_unresolved_exposure_usd":"0.05169700","predecessor_validation_case_id":"capval-openai-terra-pt1-v1","provider_invocation_count_at_reservation":0,"record_hash":"6a66fa758fa20d231a02649263fddcdb53da314b2a1f6a9c9853b10e58610ed3","record_type":"capstone_live_validation_reservation","record_version":"v2","repository_head":"440880ac85dd371a3dbe44b9e364d7df3c13c3ff","request_hash":"97f8752bb33994a00018a15ff62d79419069397b223cc5f60770def973ebc266","runtime_identity_hash":"61d7d4333adf98cebdbd8b0710443a07c56a31cc50f822252945c43428568a9e","started_at":"2026-09-01T22:42:55Z","validation_case_id":"capval-openai-terra-pt1-v2","validation_spend_ceiling_usd":"1.00000000","validation_spend_remaining_after_reservation_usd":"0.89660600"}'''
)
_V2_RESULT = json.loads(
    r'''{"authorization_hash":"9a84b4b07b81b503376a23cccdc0b953963fe4299b5f705279c348f173f9c277","candidate_id":"openai_unified_balanced_v1","completed_at":"2026-09-01T22:43:02Z","conservative_reservation_usd":"0.05169700","contract_hash":"48831c6dfafcdd00ab7e8a525d448574526ffefbfbf9c6d1bf9c105299af13be","cost_observation_status":"frozen_estimate_from_provider_usage_not_provider_billing","cumulative_worst_case_validation_exposure_usd":"0.10339400","estimated_validation_cost":{"billing_mode":"paid_standard_global","calculation_id":"exact_decimal_cost_calculation_v1","component_costs":{"cache_write_tokens":"0","cached_input_tokens":"0","output_tokens":"0.002172","uncached_input_tokens":"0.002036","web_search_calls":"0"},"context_regime":"input_tokens_at_most_272000","currency":"USD","model":"gpt-5.6-terra","pricing_observed_on":"2026-08-31","pricing_snapshot_hash":"0467643eafbe55e6e2215c9ad0e0576dac2d0d157a94418eef23382b0ec09282","pricing_snapshot_id":"pricing_snapshot_v1","pricing_snapshot_version":"v1","provider":"OpenAI","schedule_id":"openai_gpt_5_6_terra_standard_short_context_v1","total_usd":"0.004208","usage":{"cache_write_tokens":0,"cached_input_tokens":0,"output_tokens":181,"uncached_input_tokens":1018,"web_search_calls":0}},"execution_class":"capstone_live_validation","fixture_id":"PT1","http_status":200,"latency_seconds":"6.897342833050061","model":"gpt-5.6-terra","normalized_semantic_hash":"acd669b9dd5a39940c4869e87ef7224289d0ea8f1f1fdf80059467c358b98e4a","observed_validation_cost_usd":null,"parser_result":"passed","physical_provider_attempts":1,"predecessor_reservation_record_hash":"a9d604c30f16ecd4525d533955f9701ea15ed78c35cb7fff703c3e3761cd1bab","predecessor_result_record_hash":"554fdf1685a4b766698d9af255fd7921e3500a7390915957831eab440582d24e","predecessor_unresolved_exposure_usd":"0.05169700","predecessor_validation_case_id":"capval-openai-terra-pt1-v1","production_deployment":false,"provider":"OpenAI","provider_request_id":null,"provider_response_received":true,"provider_usage":{"image_usage":null,"input_tokens":1018,"output_tokens":181,"reasoning_tokens":0},"raw_response_hash":"be572ab8068291a1f87eb8ab044f49455722c3b292d02f09c80a3b50419493dd","record_hash":"1c4b25beb71569d68642e9f6d554b7473d042c779b8f26c930ca63caa9959386","record_type":"capstone_live_validation_result","record_version":"v2","repository_head":"440880ac85dd371a3dbe44b9e364d7df3c13c3ff","request_configuration_hash":"0eca58d264b7af9e48af182f8d3ce8a0a417db8201328b70fdab77b6a4bae893","request_configuration_id":"openai_terra_text_pilot_v1","request_hash":"97f8752bb33994a00018a15ff62d79419069397b223cc5f60770def973ebc266","result_status":"accepted","retry_count":0,"runtime_identity_hash":"61d7d4333adf98cebdbd8b0710443a07c56a31cc50f822252945c43428568a9e","safe_failure_classification":null,"safe_finish_reason":"completed","schema_result":"passed","scored_record":false,"semantic_summary":{"canonical_top_level_fields":["price_assessment","price_plausibility","recommendation","risk_indicators","risk_level","seller_questions","summary"],"schema_id":"text_output_schema_v1"},"source_call_id":"call-0003","started_at":"2026-09-01T22:42:55Z","strict_pilot_record":false,"validation_case_id":"capval-openai-terra-pt1-v2","validation_id":"capval-openai-terra-pt1-v2-attempt-1","validation_spend_ceiling_usd":"1.00000000","validation_spend_remaining_usd":"0.89660600","validator_result":"passed","winner_selection":false,"workload_stage":"text_analysis"}'''
)


class _Sender:
    def __init__(self, response_bytes: bytes = b"{}", *, status_code: int = 200):
        self.response_bytes = response_bytes
        self.status_code = status_code
        self.requests = []

    def send(self, request):
        self.requests.append(request)
        return HttpResponse(
            self.status_code,
            (self.response_bytes,),
            {"content-type": "application/json"},
            0.25,
        )

    def validate_runtime(self):
        return dict(RUNTIME_IDENTITY)


def _validator():
    from app.services.evaluation_capstone_cross_provider_validation import (
        build_capstone_cross_provider_validation,
    )

    return build_capstone_cross_provider_validation(
        repository_root=ROOT,
        repository_head=HEAD,
        require_clean_repository=False,
    )


def _seed_history(root: Path) -> Path:
    for directory, records in (
        ("capstone-live-validation-v1", (_V1_RESERVATION, _V1_RESULT)),
        ("capstone-live-validation-v2", (_V2_RESERVATION, _V2_RESULT)),
    ):
        state = root / directory
        state.mkdir(mode=0o700, parents=True)
        for name, value in zip(("reservation.json", "result.json"), records, strict=True):
            path = state / name
            path.write_text(
                json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            path.chmod(0o600)
    return root


def _authorization(validator, case_id):
    return validator.build_authorization_document(
        case_id=case_id,
        runtime_identity=RUNTIME_IDENTITY,
        authorized_at_utc="2026-09-01T23:00:00Z",
    )


def _rehash_authorization(document):
    changed = json.loads(json.dumps(document))
    changed["semantic_hash"] = None
    changed["semantic_hash"] = hashlib.sha256(
        json.dumps(
            changed,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return changed


def _success(validator, case_id):
    request = validator.build_request(case_id)
    value = json.loads(_synthetic_provider_envelope(request))
    if request.call.provider == "OpenAI":
        value["usage"]["input_tokens_details"] = {
            "cached_tokens": 0,
            "cache_write_tokens": 0,
        }
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def test_contract_binds_only_the_approved_sol_and_gemini_pt1_cases():
    from app.services.evaluation_capstone_cross_provider_validation import (
        CAPSTONE_CROSS_PROVIDER_TEXT_VALIDATION_STATUS,
        build_capstone_cross_provider_validation,
    )

    validator = build_capstone_cross_provider_validation(
        repository_root=ROOT,
        repository_head=HEAD,
        require_clean_repository=False,
    )

    assert CAPSTONE_CROSS_PROVIDER_TEXT_VALIDATION_STATUS == (
        "CAPSTONE_CROSS_PROVIDER_TEXT_VALIDATION_READY_AWAITING_USER"
    )
    assert tuple(case.case_id for case in validator.contract.cases) == (
        SOL_CASE_ID,
        GEMINI_CASE_ID,
    )
    assert validator.contract.total_spend_ceiling_usd == "1.00000000"
    assert validator.contract.historical_exposure_usd == "0.10339400"

    sol = validator.case(SOL_CASE_ID)
    assert sol.source_call_id == "call-0001"
    assert sol.candidate_id == "openai_unified_premium_v1"
    assert sol.provider == "OpenAI"
    assert sol.model == "gpt-5.6-sol"
    assert sol.request_configuration_id == "openai_sol_text_pilot_v1"
    assert sol.request_configuration_hash == (
        "1211deef134ed1fd723a8f0e63b054cae5c4f257138776b02b5b6f6266162caf"
    )
    assert sol.request_hash == (
        "9ddf9c22ab28c69987944c1a77043cb7ed64aed0f81c283444be4129ad47c47f"
    )
    assert sol.request_body_bytes == 6247
    assert sol.input_token_bound == 6247
    assert sol.maximum_output_tokens == 4096
    assert sol.conservative_reservation_usd == "0.10690800"
    assert sol.cumulative_exposure_usd == "0.21030200"
    assert sol.remaining_after_reservation_usd == "0.78969800"

    gemini = validator.case(GEMINI_CASE_ID)
    assert gemini.source_call_id == "call-0005"
    assert gemini.candidate_id == "gemini_unified_v1"
    assert gemini.provider == "Google Gemini"
    assert gemini.model == "gemini-3.7-flash"
    assert gemini.request_configuration_id == "gemini_flash_text_pilot_v1"
    assert gemini.request_configuration_hash == (
        "8644e02a24cff69f6619f744e02c6b55648e9463f76b30453b81dc04edbe466b"
    )
    assert gemini.request_hash == (
        "00f29bb98c9840ffb6d1e61fc080c607aa54a2b20ca862c58f862d08ed013584"
    )
    assert gemini.request_body_bytes == 6229
    assert gemini.maximum_output_tokens == 4096
    assert gemini.conservative_reservation_usd == "0.00000000"
    assert gemini.cumulative_exposure_usd == "0.21030200"
    assert gemini.remaining_after_reservation_usd == "0.78969800"


def test_historical_terra_state_is_immutable_and_both_dry_runs_are_offline(tmp_path):
    validator = _validator()
    operational_root = _seed_history(tmp_path)

    history = validator.validate_historical_state(operational_root)

    assert history["historical_conservative_exposure_usd"] == "0.10339400"
    assert [item["result_record_hash"] for item in history["states"]] == [
        "554fdf1685a4b766698d9af255fd7921e3500a7390915957831eab440582d24e",
        "1c4b25beb71569d68642e9f6d554b7473d042c779b8f26c930ca63caa9959386",
    ]
    for case_id, expected_url in (
        (SOL_CASE_ID, "https://api.openai.com/v1/responses"),
        (
            GEMINI_CASE_ID,
            "https://generativelanguage.googleapis.com/v1beta/interactions",
        ),
    ):
        sender = _Sender()
        result = validator.dry_run(
            case_id,
            operational_root=operational_root,
            transport=ConcreteLivePilotTransport(sender),
        )
        assert result["status"] == "offline_dry_run_passed"
        assert result["transport_projection"] == {
            "method": "POST",
            "url": expected_url,
            "timeout_seconds": 120,
            "redirects_allowed": False,
            "automatic_retry_count": 0,
        }
        assert result["credentials_accessed"] == 0
        assert result["provider_calls"] == 0
        assert sender.requests == []


def test_separate_hash_bound_authorizations_bind_provider_controls_and_false_gates():
    validator = _validator()
    sol = _authorization(validator, SOL_CASE_ID)
    gemini = _authorization(validator, GEMINI_CASE_ID)

    assert validator.validate_authorization(sol).case_id == SOL_CASE_ID
    assert validator.validate_authorization(gemini).case_id == GEMINI_CASE_ID
    assert sol["credential_readiness"] == {
        "environment_variable_name": "OPENAI_API_KEY",
        "status": "privately_confirmed",
    }
    assert sol["provider_control_confirmation"]["endpoint_permission"] == (
        "Responses (/v1/responses): Write"
    )
    assert gemini["credential_readiness"] == {
        "environment_variable_name": "GEMINI_API_KEY",
        "status": "privately_confirmed",
    }
    assert gemini["provider_control_confirmation"] == {
        "provider": "Google Gemini",
        "status": "confirmed",
        "billing_enabled": False,
        "tier": "free",
        "requests_per_minute": 5,
        "tokens_per_minute": 250000,
        "usage_at_setup": 0,
        "endpoint_permission": "Gemini Interactions API v1beta",
    }
    assert sol["semantic_hash"] != gemini["semantic_hash"]
    for document in (sol, gemini):
        assert document["maximum_provider_calls"] == 1
        assert document["retry_count"] == 0
        assert document["strict_pilot_execution_authorized"] is False
        assert document["scored_execution_authorized"] is False
        assert document["winner_selection_authorized"] is False
        assert document["production_deployment_authorized"] is False

    crossed = dict(sol)
    crossed["validation_case_id"] = GEMINI_CASE_ID
    with pytest.raises(CapstoneLiveValidationError):
        validator.validate_authorization(crossed)

    for field, value in (
        ("provider", "Google Gemini"),
        ("model", "gpt-5.6-terra"),
        ("request_hash", "0" * 64),
        ("maximum_provider_calls", 2),
        ("retry_count", 1),
        ("conservative_reservation_usd", "0.00000000"),
        ("scored_execution_authorized", True),
        ("winner_selection_authorized", True),
    ):
        changed = dict(sol)
        changed[field] = value
        with pytest.raises(CapstoneLiveValidationError, match="authorization_binding"):
            validator.validate_authorization(_rehash_authorization(changed))


@pytest.mark.parametrize(
    ("case_id", "credential_name", "credential_header", "expected_cost"),
    (
        (SOL_CASE_ID, "OPENAI_API_KEY", "authorization", "0.000188"),
        (GEMINI_CASE_ID, "GEMINI_API_KEY", "x-goog-api-key", "0.00000000"),
    ),
)
def test_one_mock_call_per_case_is_bounded_private_and_not_strict_state(
    tmp_path,
    case_id,
    credential_name,
    credential_header,
    expected_cost,
):
    validator = _validator()
    operational_root = _seed_history(tmp_path)
    reads = []
    sender = _Sender(_success(validator, case_id))
    resolver = LazyEnvironmentCredentialResolver(
        lambda name: reads.append(name) or CANARY
    )
    transport = ConcreteLivePilotTransport(sender)

    record = validator.execute_one(
        authorization_document=_authorization(validator, case_id),
        confirm_live=True,
        credential_resolver=resolver,
        transport=transport,
        operational_root=operational_root,
        clock=lambda: datetime(2026, 9, 1, 23, 1, tzinfo=UTC),
    )

    assert reads == [credential_name]
    assert transport.invocation_count == 1
    assert len(sender.requests) == 1
    headers = dict(sender.requests[0].headers)
    assert CANARY in headers[credential_header]
    if case_id == GEMINI_CASE_ID:
        assert headers["api-revision"] == "2026-05-20"
        assert "authorization" not in headers
        payload = json.loads(sender.requests[0].body)
        assert set(payload) == {
            "generation_config",
            "input",
            "model",
            "response_format",
            "store",
            "stream",
            "system_instruction",
        }
        assert payload["response_format"]["mime_type"] == "application/json"
        assert "instructions" not in payload
        assert "text" not in payload
    assert CANARY not in repr(sender.requests[0])
    assert record["result_status"] == "accepted"
    assert record["safe_failure_classification"] is None
    assert record["parser_result"] == "passed"
    assert record["schema_result"] == "passed"
    assert record["validator_result"] == "passed"
    assert record["estimated_validation_cost"]["total_usd"] == expected_cost
    assert record["observed_validation_cost_usd"] is None
    assert record["physical_provider_attempts"] == 1
    assert record["retry_count"] == 0
    assert record["strict_pilot_record"] is False
    assert record["scored_record"] is False
    assert record["winner_selection"] is False
    assert record["production_deployment"] is False
    assert "semantic_output" not in record
    serialized = json.dumps(record, sort_keys=True)
    assert CANARY not in serialized
    assert "Bearer" not in serialized
    for path in (operational_root / "capstone-cross-provider-text-validation-v3").rglob("*.json"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    inspection = validator.inspect_result(case_id, operational_root)
    assert inspection["record_hash"] == record["record_hash"]

    with pytest.raises(CapstoneLiveValidationError, match="case_already_reserved"):
        validator.execute_one(
            authorization_document=_authorization(validator, case_id),
            confirm_live=True,
            credential_resolver=resolver,
            transport=transport,
            operational_root=operational_root,
        )
    assert transport.invocation_count == 1


def test_runtime_or_confirmation_failure_precedes_credentials_state_and_transport(tmp_path):
    validator = _validator()
    operational_root = _seed_history(tmp_path)
    reads = []
    sender = _Sender(_success(validator, SOL_CASE_ID))
    transport = ConcreteLivePilotTransport(sender)
    resolver = LazyEnvironmentCredentialResolver(
        lambda name: reads.append(name) or CANARY
    )

    with pytest.raises(
        CapstoneLiveValidationError,
        match="explicit_live_confirmation_required",
    ):
        validator.execute_one(
            authorization_document=_authorization(validator, SOL_CASE_ID),
            confirm_live=False,
            credential_resolver=resolver,
            transport=transport,
            operational_root=operational_root,
        )
    assert reads == []
    assert sender.requests == []
    assert not (operational_root / "capstone-cross-provider-text-validation-v3").exists()

    sender.validate_runtime = lambda: {
        **RUNTIME_IDENTITY,
        "http_client_version": "0.29.0",
    }
    with pytest.raises(CapstoneLiveValidationError, match="runtime_identity_mismatch"):
        validator.execute_one(
            authorization_document=_authorization(validator, SOL_CASE_ID),
            confirm_live=True,
            credential_resolver=resolver,
            transport=ConcreteLivePilotTransport(sender),
            operational_root=operational_root,
        )
    assert reads == []
    assert sender.requests == []


def test_gemini_bound_is_far_below_supplied_free_tier_rate_limits():
    gemini = _validator().case(GEMINI_CASE_ID)

    assert gemini.provider_limits == {
        "requests_per_minute": 5,
        "tokens_per_minute": 250000,
        "usage_at_setup": 0,
    }
    assert 1 <= gemini.provider_limits["requests_per_minute"]
    assert gemini.input_token_bound + gemini.maximum_output_tokens == 10325
    assert 10325 < gemini.provider_limits["tokens_per_minute"]
