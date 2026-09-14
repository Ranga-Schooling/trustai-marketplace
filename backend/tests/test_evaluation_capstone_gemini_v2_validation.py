"""Provider-free tests for the corrected single-use Gemini/PT1 V2 path."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import stat
import subprocess

import pytest

from app.services.evaluation_capstone_gemini_v2_validation import (
    CAPSTONE_GEMINI_V2_VALIDATION_STATUS,
    build_capstone_gemini_v2_validation,
)
from app.services.evaluation_capstone_gemini_v2_validation_cli import run_cli
from app.services.evaluation_capstone_live_validation import (
    CapstoneLiveValidationError,
)
from app.services.evaluation_live_transport import (
    ConcreteLivePilotTransport,
    HttpResponse,
    LazyEnvironmentCredentialResolver,
)
from app.services.evaluation_pilot_runner import _synthetic_provider_envelope
from tests.test_evaluation_capstone_cross_provider_validation import (
    RUNTIME_IDENTITY,
    _seed_history,
)


ROOT = Path(__file__).resolve().parents[2]
HEAD = subprocess.run(
    ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()
CASE_ID = "capval-gemini-flash-pt1-v2"
CANARY = "gemini-v2-test-canary-not-a-real-secret"

_SOL_RESERVATION = json.loads(
    r'''{"authorization_hash":"45b14e2240ed749ac430f82cd792d4cc301e451d48d1fdb0a3b68221b4878e61","billing_context":"paid_standard_global","conservative_reservation_usd":"0.10690800","contract_hash":"fa141065f8fe374d4b43409cefb2fec58e66f3f949d733ea4bf9cdc254635617","cumulative_worst_case_validation_exposure_usd":"0.21030200","execution_class":"capstone_live_validation","historical_conservative_exposure_usd":"0.10339400","historical_predecessor_validation_case_id":"capval-openai-terra-pt1-v2","provider_invocation_count_at_reservation":0,"record_hash":"115405478d45a6cedfb406bf774dfd9a7f47df186f01513f557797c1e815be2a","record_type":"capstone_live_validation_reservation","record_version":"v3","repository_head":"6f271faa7405c3f6ecf7fc5f81f874a295a01601","request_hash":"9ddf9c22ab28c69987944c1a77043cb7ed64aed0f81c283444be4129ad47c47f","runtime_identity_hash":"61d7d4333adf98cebdbd8b0710443a07c56a31cc50f822252945c43428568a9e","started_at":"2026-09-01T23:14:18Z","terra_v1_reservation_record_hash":"a9d604c30f16ecd4525d533955f9701ea15ed78c35cb7fff703c3e3761cd1bab","terra_v1_result_record_hash":"554fdf1685a4b766698d9af255fd7921e3500a7390915957831eab440582d24e","terra_v2_reservation_record_hash":"6a66fa758fa20d231a02649263fddcdb53da314b2a1f6a9c9853b10e58610ed3","terra_v2_result_record_hash":"1c4b25beb71569d68642e9f6d554b7473d042c779b8f26c930ca63caa9959386","validation_case_id":"capval-openai-sol-pt1-v1","validation_spend_ceiling_usd":"1.00000000","validation_spend_remaining_after_reservation_usd":"0.78969800"}'''
)
_SOL_RESULT = json.loads(
    r'''{"authorization_hash":"45b14e2240ed749ac430f82cd792d4cc301e451d48d1fdb0a3b68221b4878e61","billing_context":"paid_standard_global","candidate_id":"openai_unified_premium_v1","completed_at":"2026-09-01T23:14:22Z","conservative_reservation_usd":"0.10690800","contract_hash":"fa141065f8fe374d4b43409cefb2fec58e66f3f949d733ea4bf9cdc254635617","cost_observation_status":"frozen_estimate_from_provider_usage_not_provider_billing","cumulative_worst_case_validation_exposure_usd":"0.21030200","estimated_validation_cost":{"billing_mode":"paid_standard_global","calculation_id":"exact_decimal_cost_calculation_v1","component_costs":{"cache_write_tokens":"0","cached_input_tokens":"0","output_tokens":"0.00302","uncached_input_tokens":"0.004072","web_search_calls":"0"},"context_regime":"input_tokens_at_most_272000","currency":"USD","model":"gpt-5.6-sol","pricing_observed_on":"2026-08-31","pricing_snapshot_hash":"0467643eafbe55e6e2215c9ad0e0576dac2d0d157a94418eef23382b0ec09282","pricing_snapshot_id":"pricing_snapshot_v1","pricing_snapshot_version":"v1","provider":"OpenAI","schedule_id":"openai_gpt_5_6_sol_standard_short_context_v1","total_usd":"0.007092","usage":{"cache_write_tokens":0,"cached_input_tokens":0,"output_tokens":151,"uncached_input_tokens":1018,"web_search_calls":0}},"execution_class":"capstone_live_validation","fixture_id":"PT1","historical_conservative_exposure_usd":"0.10339400","historical_predecessor_validation_case_id":"capval-openai-terra-pt1-v2","http_status":200,"latency_seconds":"4.029280124988873","model":"gpt-5.6-sol","normalized_semantic_hash":"8f3e1960a0fb8e49170cba210197bd0a16a61782932bd7f9644a2ca57955627d","observed_validation_cost_usd":null,"parser_result":"passed","physical_provider_attempts":1,"production_deployment":false,"provider":"OpenAI","provider_request_id":null,"provider_response_received":true,"provider_usage":{"image_usage":null,"input_tokens":1018,"output_tokens":151,"reasoning_tokens":0},"raw_response_hash":"13e1367c59237d999f216ec461670908e3b08b5f096ad9dd961f59a4f36548bf","record_hash":"352beabadd1ee86c0bc51f7b4c20dcfc66d2fd1574a947f1ef64660e43b4e167","record_type":"capstone_live_validation_result","record_version":"v3","repository_head":"6f271faa7405c3f6ecf7fc5f81f874a295a01601","request_configuration_hash":"1211deef134ed1fd723a8f0e63b054cae5c4f257138776b02b5b6f6266162caf","request_configuration_id":"openai_sol_text_pilot_v1","request_hash":"9ddf9c22ab28c69987944c1a77043cb7ed64aed0f81c283444be4129ad47c47f","result_status":"accepted","retry_count":0,"runtime_identity_hash":"61d7d4333adf98cebdbd8b0710443a07c56a31cc50f822252945c43428568a9e","safe_failure_classification":null,"safe_finish_reason":"completed","schema_result":"passed","scored_record":false,"semantic_summary":{"canonical_top_level_fields":["price_assessment","price_plausibility","recommendation","risk_indicators","risk_level","seller_questions","summary"],"schema_id":"text_output_schema_v1"},"source_call_id":"call-0001","started_at":"2026-09-01T23:14:18Z","strict_pilot_record":false,"terra_v1_reservation_record_hash":"a9d604c30f16ecd4525d533955f9701ea15ed78c35cb7fff703c3e3761cd1bab","terra_v1_result_record_hash":"554fdf1685a4b766698d9af255fd7921e3500a7390915957831eab440582d24e","terra_v2_reservation_record_hash":"6a66fa758fa20d231a02649263fddcdb53da314b2a1f6a9c9853b10e58610ed3","terra_v2_result_record_hash":"1c4b25beb71569d68642e9f6d554b7473d042c779b8f26c930ca63caa9959386","validation_case_id":"capval-openai-sol-pt1-v1","validation_id":"capval-openai-sol-pt1-v1-attempt-1","validation_spend_ceiling_usd":"1.00000000","validation_spend_remaining_usd":"0.78969800","validator_result":"passed","winner_selection":false,"workload_stage":"text_analysis"}'''
)
_GEMINI_V1_RESERVATION = json.loads(
    r'''{"authorization_hash":"84a0ccbf16292ed774a32e7d9640481e868488336c35533af22a4afe5b2cf022","billing_context":"provider_free_tier_no_billing_enabled","conservative_reservation_usd":"0.00000000","contract_hash":"fa141065f8fe374d4b43409cefb2fec58e66f3f949d733ea4bf9cdc254635617","cumulative_worst_case_validation_exposure_usd":"0.21030200","execution_class":"capstone_live_validation","historical_conservative_exposure_usd":"0.10339400","historical_predecessor_validation_case_id":"capval-openai-terra-pt1-v2","provider_invocation_count_at_reservation":0,"record_hash":"a891cb4fb77d86c073ff204fbdaffd0ff5d05d3e05a9c88d778e273a3b6e4c01","record_type":"capstone_live_validation_reservation","record_version":"v3","repository_head":"6f271faa7405c3f6ecf7fc5f81f874a295a01601","request_hash":"00f29bb98c9840ffb6d1e61fc080c607aa54a2b20ca862c58f862d08ed013584","runtime_identity_hash":"61d7d4333adf98cebdbd8b0710443a07c56a31cc50f822252945c43428568a9e","started_at":"2026-09-01T23:18:45Z","terra_v1_reservation_record_hash":"a9d604c30f16ecd4525d533955f9701ea15ed78c35cb7fff703c3e3761cd1bab","terra_v1_result_record_hash":"554fdf1685a4b766698d9af255fd7921e3500a7390915957831eab440582d24e","terra_v2_reservation_record_hash":"6a66fa758fa20d231a02649263fddcdb53da314b2a1f6a9c9853b10e58610ed3","terra_v2_result_record_hash":"1c4b25beb71569d68642e9f6d554b7473d042c779b8f26c930ca63caa9959386","validation_case_id":"capval-gemini-flash-pt1-v1","validation_spend_ceiling_usd":"1.00000000","validation_spend_remaining_after_reservation_usd":"0.78969800"}'''
)
_GEMINI_V1_RESULT = json.loads(
    r'''{"authorization_hash":"84a0ccbf16292ed774a32e7d9640481e868488336c35533af22a4afe5b2cf022","billing_context":"provider_free_tier_no_billing_enabled","candidate_id":"gemini_unified_v1","completed_at":"2026-09-01T23:18:45Z","conservative_reservation_usd":"0.00000000","contract_hash":"fa141065f8fe374d4b43409cefb2fec58e66f3f949d733ea4bf9cdc254635617","cost_observation_status":"not_determinable","cumulative_worst_case_validation_exposure_usd":"0.21030200","estimated_validation_cost":null,"execution_class":"capstone_live_validation","fixture_id":"PT1","historical_conservative_exposure_usd":"0.10339400","historical_predecessor_validation_case_id":"capval-openai-terra-pt1-v2","http_status":400,"latency_seconds":"0.28190220904070884","model":"gemini-3.7-flash","normalized_semantic_hash":null,"observed_validation_cost_usd":null,"parser_result":"not_reached","physical_provider_attempts":1,"production_deployment":false,"provider":"Google Gemini","provider_request_id":null,"provider_response_received":true,"provider_usage":null,"raw_response_hash":"9cfc3b4a362e7f72f74843cf60e0c842aadcd07546c919afb12c1189a327fc5c","record_hash":"222a10f499873278a526e12bd1c44b62d104a07f477162b1bba75860db488da8","record_type":"capstone_live_validation_result","record_version":"v3","repository_head":"6f271faa7405c3f6ecf7fc5f81f874a295a01601","request_configuration_hash":"8644e02a24cff69f6619f744e02c6b55648e9463f76b30453b81dc04edbe466b","request_configuration_id":"gemini_flash_text_pilot_v1","request_hash":"00f29bb98c9840ffb6d1e61fc080c607aa54a2b20ca862c58f862d08ed013584","result_status":"stopped","retry_count":0,"runtime_identity_hash":"61d7d4333adf98cebdbd8b0710443a07c56a31cc50f822252945c43428568a9e","safe_failure_classification":"http_failure","safe_finish_reason":"http_failure","schema_result":"not_reached","scored_record":false,"semantic_summary":null,"source_call_id":"call-0005","started_at":"2026-09-01T23:18:45Z","strict_pilot_record":false,"terra_v1_reservation_record_hash":"a9d604c30f16ecd4525d533955f9701ea15ed78c35cb7fff703c3e3761cd1bab","terra_v1_result_record_hash":"554fdf1685a4b766698d9af255fd7921e3500a7390915957831eab440582d24e","terra_v2_reservation_record_hash":"6a66fa758fa20d231a02649263fddcdb53da314b2a1f6a9c9853b10e58610ed3","terra_v2_result_record_hash":"1c4b25beb71569d68642e9f6d554b7473d042c779b8f26c930ca63caa9959386","validation_case_id":"capval-gemini-flash-pt1-v1","validation_id":"capval-gemini-flash-pt1-v1-attempt-1","validation_spend_ceiling_usd":"1.00000000","validation_spend_remaining_usd":"0.78969800","validator_result":"not_reached","winner_selection":false,"workload_stage":"text_analysis"}'''
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
    return build_capstone_gemini_v2_validation(
        repository_root=ROOT,
        repository_head=HEAD,
        require_clean_repository=False,
    )


def _write_record(path: Path, value: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def _seed_complete_history(root: Path) -> Path:
    _seed_history(root)
    v3 = root / "capstone-cross-provider-text-validation-v3"
    for case_id, reservation, result in (
        ("capval-openai-sol-pt1-v1", _SOL_RESERVATION, _SOL_RESULT),
        (
            "capval-gemini-flash-pt1-v1",
            _GEMINI_V1_RESERVATION,
            _GEMINI_V1_RESULT,
        ),
    ):
        _write_record(v3 / case_id / "reservation.json", reservation)
        _write_record(v3 / case_id / "result.json", result)
    return root


def _authorization(validator):
    return validator.build_authorization_document(
        case_id=CASE_ID,
        runtime_identity=RUNTIME_IDENTITY,
        authorized_at_utc="2026-09-01T23:30:00Z",
    )


def test_contract_binds_only_corrected_gemini_v2_request():
    validator = _validator()
    case = validator.case(CASE_ID)
    request = validator.build_request(CASE_ID)

    assert CAPSTONE_GEMINI_V2_VALIDATION_STATUS == (
        "CAPSTONE_GEMINI_V2_VALIDATION_READY_AWAITING_USER"
    )
    assert validator.contract.semantic_hash == (
        "8a9632559202da1849f83afc4cd38e5a20d4cb29b2cff7c57f9705c528722a7a"
    )
    assert case.predecessor_case_id == "capval-gemini-flash-pt1-v1"
    assert case.request_hash == (
        "7ba77e1a55b8171d55d95aff39a7ffb171f8ba4eaf91a3dba342754ec4f57640"
    )
    assert request.payload_hash == case.request_hash
    assert len(request.payload_json) == 6235
    assert request.payload["input"][0]["type"] == "user_input"
    assert "role" not in request.payload["input"][0]
    assert case.conservative_reservation_usd == "0.00000000"
    assert case.cumulative_exposure_usd == "0.21030200"
    assert case.remaining_after_reservation_usd == "0.78969800"


def test_history_dry_run_authorization_and_preflight_are_offline(tmp_path):
    validator = _validator()
    root = _seed_complete_history(tmp_path / "state")
    sender = _Sender()
    transport = ConcreteLivePilotTransport(sender)

    projection = validator.dry_run(
        CASE_ID, operational_root=root, transport=transport
    )
    authorization = _authorization(validator)
    binding, runtime, outgoing = validator.validate_offline_preflight(
        authorization_document=authorization,
        operational_root=root,
        transport=transport,
    )

    assert projection["status"] == "offline_dry_run_passed"
    assert projection["historical_state"]["gemini_v1"]["http_status"] == 400
    assert projection["historical_state"]["sol"]["result_status"] == "accepted"
    assert projection["credentials_accessed"] == 0
    assert projection["provider_calls"] == 0
    assert binding.case_id == CASE_ID
    assert runtime == RUNTIME_IDENTITY
    assert outgoing["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/interactions"
    )
    assert sender.requests == []


def test_one_mock_success_is_bounded_private_and_not_strict_state(tmp_path):
    validator = _validator()
    root = _seed_complete_history(tmp_path / "state")
    request = validator.build_request(CASE_ID)
    response = _synthetic_provider_envelope(request)
    sender = _Sender(response)
    reads = []
    resolver = LazyEnvironmentCredentialResolver(
        lambda name: reads.append(name) or CANARY
    )
    transport = ConcreteLivePilotTransport(sender)

    record = validator.execute_one(
        authorization_document=_authorization(validator),
        confirm_live=True,
        credential_resolver=resolver,
        transport=transport,
        operational_root=root,
        clock=lambda: datetime(2026, 9, 1, 23, 31, tzinfo=UTC),
    )

    assert reads == ["GEMINI_API_KEY"]
    assert transport.invocation_count == 1
    assert len(sender.requests) == 1
    outgoing = json.loads(sender.requests[0].body)
    assert outgoing["input"][0]["type"] == "user_input"
    assert CANARY in dict(sender.requests[0].headers)["x-goog-api-key"]
    assert CANARY not in repr(sender.requests[0])
    assert record["result_status"] == "accepted"
    assert record["parser_result"] == "passed"
    assert record["schema_result"] == "passed"
    assert record["validator_result"] == "passed"
    assert record["estimated_validation_cost"]["total_usd"] == "0.00000000"
    assert record["physical_provider_attempts"] == 1
    assert record["retry_count"] == 0
    assert record["strict_pilot_record"] is False
    assert record["scored_record"] is False
    assert record["winner_selection"] is False
    assert record["production_deployment"] is False
    assert CANARY not in json.dumps(record, sort_keys=True)
    for path in (root / "capstone-gemini-text-validation-v4").rglob("*.json"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(CapstoneLiveValidationError, match="case_already_reserved"):
        validator.execute_one(
            authorization_document=_authorization(validator),
            confirm_live=True,
            credential_resolver=resolver,
            transport=ConcreteLivePilotTransport(_Sender(response)),
            operational_root=root,
        )


def test_http_failure_is_hashed_safe_not_parsed_and_never_retried(tmp_path):
    validator = _validator()
    root = _seed_complete_history(tmp_path / "state")
    provider_prose = b'{"error":{"message":"private provider prose"}}'
    sender = _Sender(provider_prose, status_code=400)
    record = validator.execute_one(
        authorization_document=_authorization(validator),
        confirm_live=True,
        credential_resolver=LazyEnvironmentCredentialResolver(lambda _name: CANARY),
        transport=ConcreteLivePilotTransport(sender),
        operational_root=root,
        clock=lambda: datetime(2026, 9, 1, 23, 32, tzinfo=UTC),
    )

    assert len(sender.requests) == 1
    assert record["http_status"] == 400
    assert record["result_status"] == "stopped"
    assert record["safe_failure_classification"] == "http_failure"
    assert record["raw_response_hash"] == hashlib.sha256(provider_prose).hexdigest()
    assert record["parser_result"] == "not_reached"
    assert record["schema_result"] == "not_reached"
    assert record["validator_result"] == "not_reached"
    assert record["retry_count"] == 0
    assert "private provider prose" not in json.dumps(record, sort_keys=True)


def test_cli_authorization_and_preflight_are_offline(tmp_path, capsys):
    root = _seed_complete_history(tmp_path / "state")
    sender = _Sender()
    factory = lambda: sender
    assert run_cli(
        [
            "authorization",
            "--repository-head",
            HEAD,
            "--case-id",
            CASE_ID,
            "--authorized-at-utc",
            "2026-09-01T23:30:00Z",
            "--confirm-explicit-user-authorization",
        ],
        operational_root=root,
        sender_factory=factory,
        require_clean_repository=False,
    ) == 0
    authorization = json.loads(capsys.readouterr().out)
    path = tmp_path / "authorization.json"
    path.write_text(json.dumps(authorization), encoding="utf-8")
    assert run_cli(
        [
            "preflight",
            "--repository-head",
            HEAD,
            "--case-id",
            CASE_ID,
            "--authorization",
            str(path),
        ],
        operational_root=root,
        sender_factory=factory,
        require_clean_repository=False,
    ) == 0
    projection = json.loads(capsys.readouterr().out)
    assert projection["status"] == "ready_for_one_explicitly_confirmed_live_call"
    assert projection["provider_calls"] == 0
    assert projection["credentials_accessed"] == 0
    assert sender.requests == []


def test_live_confirmation_failure_precedes_credentials_and_sender(tmp_path, capsys):
    root = _seed_complete_history(tmp_path / "state")
    reads = []
    sender = _Sender()
    path = tmp_path / "authorization.json"
    path.write_text("{}", encoding="utf-8")
    assert run_cli(
        [
            "execute",
            "--repository-head",
            HEAD,
            "--case-id",
            CASE_ID,
            "--authorization",
            str(path),
        ],
        operational_root=root,
        environment_getter=lambda name: reads.append(name) or CANARY,
        sender_factory=lambda: sender,
        require_clean_repository=False,
    ) == 2
    assert json.loads(capsys.readouterr().out) == {
        "status": "blocked",
        "reason": "explicit_live_confirmation_required",
    }
    assert reads == []
    assert sender.requests == []
