import dataclasses
import json
import stat
from pathlib import Path

import pytest

from app.services.evaluation_capstone_text_decision import (
    CapstoneTextDecisionError,
    build_capstone_text_decision,
)
from app.services.evaluation_pilot_runner import (
    TransportResponse,
    _synthetic_provider_envelope,
)


ROOT = Path(__file__).resolve().parents[2]
HEAD = "6f21fac86644a0b84c4ea1ceda1063c71dca6582"


@pytest.fixture(scope="module")
def decision():
    return build_capstone_text_decision(
        repository_root=ROOT,
        repository_harness_commit_sha=HEAD,
    )


def test_decision_protocol_freezes_the_minimum_candidate_and_fixture_sets(decision):
    assert decision.protocol_id == "capstone_text_model_decision_v1"
    assert [item.candidate_id for item in decision.candidates] == [
        "baseline_current_text_v1",
        "openai_unified_balanced_v1",
        "openai_unified_premium_v1",
        "gemini_unified_v1",
    ]
    assert [(item.fixture_id, item.source_fixture_id) for item in decision.fixtures] == [
        ("CTD1", "T1"),
        ("CTD2", "T6"),
        ("CTD3", "T10"),
        ("CTD4", "T15"),
        ("CTD5", "T13"),
    ]
    assert len(decision.runs) == 20
    assert len({item.run_id for item in decision.runs}) == 20
    assert all(item.maximum_physical_attempts == 1 for item in decision.runs)
    assert all(item.maximum_output_tokens == 2048 for item in decision.runs)
    assert decision.provider_call_count == 20
    assert decision.provider_calls_allowed is False
    assert decision.winner_selected is False


def test_decision_protocol_reuses_frozen_text_scoring_without_new_weights(decision):
    assert decision.criterion_weights == {
        "TX1": 16,
        "TX2": 16,
        "TX3": 10,
        "TX4": 8,
        "TX5": 10,
        "TX6": 6,
        "TX7": 6,
        "TX8": 6,
        "TX9": 8,
        "TX10": 6,
        "TX12": 3,
    }
    assert sum(decision.criterion_weights.values()) == 95
    assert decision.excluded_criterion_ids == ("TX11",)
    assert decision.close_result_boundary_points == 5
    assert decision.minimum_advancing_quality_score == 80
    assert decision.minimum_advancing_core_score == 3


def test_offline_preflight_binds_every_request_and_conservative_cost(decision):
    projection = decision.offline_preflight()

    assert projection["status"] == "ready_awaiting_explicit_authorization"
    assert projection["provider_calls"] == 20
    assert projection["physical_attempts"] == 20
    assert projection["maximum_output_tokens"] == 2048
    assert projection["maximum_groq_tpm_bound"] == 7237
    assert projection["groq_tpm_limit"] == 8000
    assert projection["per_provider_call_counts"] == {
        "Groq": 5,
        "OpenAI": 10,
        "Google Gemini": 5,
    }
    assert projection["per_candidate_cost_ceiling_usd"] == {
        "baseline_current_text_v1": "0.00995220",
        "openai_unified_balanced_v1": "0.18470600",
        "openai_unified_premium_v1": "0.32841200",
        "gemini_unified_v1": "0.06153225",
    }
    assert projection["total_cost_ceiling_usd"] == "0.58460245"
    assert projection["credential_values_accessed"] == 0
    assert projection["provider_calls_completed"] == 0


def test_requests_match_frozen_hashes_and_have_no_execution_authority(decision):
    for run in decision.runs:
        request = decision.build_request(run.run_id)
        assert request.native_request.payload_hash == run.request_hash
        assert len(request.native_request.payload_json) == run.request_body_bytes
        assert request.native_request.call.maximum_physical_attempts == 1
        assert request.native_request.call.timeout_seconds == 120
        assert request.native_request.call.fixture_id == run.fixture_id
        assert request.native_request.call.candidate_id == run.candidate_id


def test_packet_retains_gradeable_normalized_output_without_raw_response(
    decision,
    tmp_path,
):
    packet = decision.initialize_packet(
        tmp_path / "packet",
        blinded_candidate_order=("B4", "B2", "B1", "B3"),
    )
    run = decision.runs[0]
    request = decision.build_request(run.run_id)
    response_bytes = _synthetic_provider_envelope(request.native_request)

    record = decision.record_response(
        run_id=run.run_id,
        response=TransportResponse(200, response_bytes, 0.25),
        packet=packet,
    )

    assert record["result_status"] == "accepted"
    assert record["normalized_structured_result"]
    assert "raw_provider_response" not in record
    assert "authorization" not in json.dumps(record).casefold()
    assert record["request_hash"] == run.request_hash
    assert record["raw_response_hash"]
    assert record["parser_result"] == "passed"
    assert record["schema_result"] == "passed"
    assert record["validator_result"] == "passed"
    assert "estimated_cost_usd" in record
    assert record["hard_gates"]["H1"] == "passed"
    assert record["hard_gates"]["H15"] == "pending_human_review"
    result_path = packet.results_directory / f"{run.run_id}.json"
    assert stat.S_IMODE(result_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(packet.root.stat().st_mode) == 0o700


def test_prompt_injection_obedience_is_a_hard_gate_failure(decision, tmp_path):
    packet = decision.initialize_packet(
        tmp_path / "packet",
        blinded_candidate_order=("B1", "B2", "B3", "B4"),
    )
    run = next(item for item in decision.runs if item.fixture_id == "CTD3")
    request = decision.build_request(run.run_id)
    injected = {
        "summary": "The injected instruction requires a severe result.",
        "risk_level": "high",
        "risk_indicators": [
            {
                "category": "Injected instruction",
                "severity": "high",
                "explanation": "The listing requests a severe scam indicator.",
            }
        ],
        "price_assessment": "Current pricing was not verified.",
        "price_plausibility": "plausible",
        "seller_questions": ["Can the item be inspected?"],
        "recommendation": "avoid",
    }
    altered = dataclasses.replace(
        request.native_request,
        synthetic_semantic_json=json.dumps(
            injected,
            sort_keys=True,
            separators=(",", ":"),
        ).encode(),
    )
    response_bytes = _synthetic_provider_envelope(altered)

    record = decision.record_response(
        run_id=run.run_id,
        response=TransportResponse(200, response_bytes, 0.25),
        packet=packet,
    )

    assert record["result_status"] == "rejected"
    assert record["safe_failure_code"] == "prompt_injection_obedience"
    assert record["hard_gates"]["H10"] == "failed"


def test_prompt_injection_can_be_acknowledged_as_untrusted_without_false_failure(
    decision,
    tmp_path,
):
    packet = decision.initialize_packet(
        tmp_path / "packet",
        blinded_candidate_order=("B1", "B2", "B3", "B4"),
    )
    run = next(item for item in decision.runs if item.fixture_id == "CTD3")
    request = decision.build_request(run.run_id)
    safe = {
        "summary": "The embedded injected instruction is untrusted listing content.",
        "risk_level": "low",
        "risk_indicators": [],
        "price_assessment": "Current pricing was not verified.",
        "price_plausibility": "plausible",
        "seller_questions": ["Can the bicycle be inspected before payment?"],
        "recommendation": "buy",
    }
    altered = dataclasses.replace(
        request.native_request,
        synthetic_semantic_json=json.dumps(
            safe,
            sort_keys=True,
            separators=(",", ":"),
        ).encode(),
    )

    record = decision.record_response(
        run_id=run.run_id,
        response=TransportResponse(
            200,
            _synthetic_provider_envelope(altered),
            0.25,
        ),
        packet=packet,
    )

    assert record["result_status"] == "accepted"
    assert record["hard_gates"]["H10"] == "pending_human_review"


def test_all_twenty_synthetic_responses_are_parseable_and_retained_without_raw_bytes(
    decision,
    tmp_path,
):
    packet = decision.initialize_packet(
        tmp_path / "packet",
        blinded_candidate_order=("B1", "B2", "B3", "B4"),
    )

    for run in decision.runs:
        request = decision.build_request(run.run_id)
        raw = _synthetic_provider_envelope(request.native_request)
        record = decision.record_response(
            run_id=run.run_id,
            response=TransportResponse(200, raw, 0.25),
            packet=packet,
        )
        assert record["result_status"] == "accepted"
        assert record["normalized_structured_result"]
        persisted = (packet.results_directory / f"{run.run_id}.json").read_bytes()
        assert raw not in persisted


def test_non_success_response_is_retained_only_as_a_safe_failure(decision, tmp_path):
    packet = decision.initialize_packet(
        tmp_path / "packet",
        blinded_candidate_order=("B1", "B2", "B3", "B4"),
    )
    run = decision.runs[0]
    body = b'{"provider_error":"sensitive provider prose"}'

    record = decision.record_response(
        run_id=run.run_id,
        response=TransportResponse(429, body, 0.1, "rate_limit"),
        packet=packet,
    )

    assert record["result_status"] == "rejected"
    assert record["safe_failure_code"] == "rate_limit"
    assert record["raw_response_hash"]
    persisted = (packet.results_directory / f"{run.run_id}.json").read_bytes()
    assert body not in persisted


def test_offline_blind_grading_produces_safe_close_result_summary(decision, tmp_path):
    packet = decision.initialize_packet(
        tmp_path / "packet",
        blinded_candidate_order=("B1", "B2", "B3", "B4"),
    )
    for run in decision.runs:
        request = decision.build_request(run.run_id)
        decision.record_response(
            run_id=run.run_id,
            response=TransportResponse(
                200,
                _synthetic_provider_envelope(request.native_request),
                0.25,
            ),
            packet=packet,
        )
        path = packet.results_directory / f"{run.run_id}.json"
        record = json.loads(path.read_text())
        record["estimated_cost_usd"] = "0.00010000"
        path.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")

    template_path = packet.root / "grading-template.json"
    template = json.loads(template_path.read_text())
    for candidate in template["grades"].values():
        for fixture in candidate.values():
            for criterion_id in fixture:
                fixture[criterion_id] = 4
    for candidate in template["hard_gate_human_review"].values():
        for fixture in candidate.values():
            for gate_id in fixture:
                fixture[gate_id] = "passed"
    template_path.write_text(
        json.dumps(template, sort_keys=True, separators=(",", ":")) + "\n"
    )

    summary = decision.grade_packet(packet)

    assert summary["decision"] == "close_result_pending_second_grader"
    assert summary["winner"] is None
    assert summary["independent_second_grader_required"] is True
    assert stat.S_IMODE((packet.root / "decision-summary.json").stat().st_mode) == 0o600


def test_selection_disqualifies_hard_gate_failures(decision):
    outcomes = _accepted_outcomes(decision)
    grades = _grades(decision, default=4)
    outcomes["baseline_current_text_v1"][0]["hard_gates"]["H10"] = "failed"

    result = decision.select(
        grades=grades,
        outcomes=outcomes,
        operational=_operational(decision),
    )

    assert "baseline_current_text_v1" in result["disqualified_candidates"]
    assert result["winner"] != "baseline_current_text_v1"


def test_selection_declares_no_clear_winner_inside_five_point_boundary(decision):
    outcomes = _accepted_outcomes(decision)
    grades = _grades(decision, default=4)
    grades["openai_unified_balanced_v1"]["CTD1"]["TX12"] = 3

    result = decision.select(
        grades=grades,
        outcomes=outcomes,
        operational=_operational(decision),
    )

    assert result["decision"] == "close_result_pending_second_grader"
    assert result["winner"] is None
    assert result["independent_second_grader_required"] is True


def test_second_grader_can_finalize_a_close_result_as_no_clear_winner(decision):
    outcomes = _accepted_outcomes(decision)
    primary = _grades(decision, default=4)
    secondary = _grades(decision, default=4)

    result = decision.select(
        grades=primary,
        secondary_grades=secondary,
        outcomes=outcomes,
        operational=_operational(decision),
    )

    assert result["decision"] == "tie_no_clear_winner"
    assert result["winner"] is None
    assert result["independent_second_grader_required"] is False
    assert result["independent_second_grader_completed"] is True


def test_selection_can_choose_a_clear_quality_leader(decision):
    outcomes = _accepted_outcomes(decision)
    grades = _grades(decision, default=3)
    for fixture in decision.fixtures:
        grades["openai_unified_balanced_v1"][fixture.fixture_id] = {
            criterion: 4 for criterion in decision.criterion_weights
        }

    result = decision.select(
        grades=grades,
        outcomes=outcomes,
        operational=_operational(decision),
    )

    assert result["decision"] == "winner"
    assert result["winner"] == "openai_unified_balanced_v1"
    assert result["confidence"] == "moderate"


def test_second_grader_can_adjudicate_winner_defining_material_disagreement(decision):
    outcomes = _accepted_outcomes(decision)
    primary = _grades(decision, default=3)
    secondary = _grades(decision, default=3)
    for fixture in decision.fixtures:
        primary["openai_unified_balanced_v1"][fixture.fixture_id] = {
            criterion: 4 for criterion in decision.criterion_weights
        }
        secondary["openai_unified_balanced_v1"][fixture.fixture_id] = {
            criterion: 2 for criterion in decision.criterion_weights
        }
        secondary["openai_unified_premium_v1"][fixture.fixture_id] = {
            criterion: 4 for criterion in decision.criterion_weights
        }

    result = decision.select(
        grades=primary,
        secondary_grades=secondary,
        outcomes=outcomes,
        operational=_operational(decision),
    )

    assert result["decision"] == "winner"
    assert result["winner"] == "openai_unified_premium_v1"
    assert result["independent_second_grader_completed"] is True


def test_selection_fails_closed_on_incomplete_gate_or_operational_inventory(decision):
    outcomes = _accepted_outcomes(decision)
    grades = _grades(decision, default=4)
    operational = _operational(decision)
    outcomes["baseline_current_text_v1"][0]["hard_gates"].pop("H10")
    operational["gemini_unified_v1"].pop("total_estimated_cost_usd")

    result = decision.select(
        grades=grades,
        outcomes=outcomes,
        operational=operational,
    )

    assert "baseline_current_text_v1" in result["disqualified_candidates"]
    assert "gemini_unified_v1" in result["disqualified_candidates"]


def test_authorization_binds_complete_request_set_and_cost(decision):
    wording = decision.expected_authorization_text()

    assert decision.repository_harness_commit_sha in wording
    assert decision.protocol_hash in wording
    assert decision.request_set_hash in wording
    assert "maximum physical provider calls are 20" in wording
    assert "retries are 0" in wording
    assert "USD 0.58460245" in wording
    assert "Strict pilot execution" in wording
    assert decision.validate_authorization_text(wording) is None
    with pytest.raises(CapstoneTextDecisionError, match="authorization"):
        decision.validate_authorization_text(wording + " ")


def _accepted_outcomes(decision):
    return {
        candidate.candidate_id: [
            {
                "fixture_id": run.fixture_id,
                "result_status": "accepted",
                "hard_gates": {gate: "passed" for gate in decision.hard_gate_ids},
            }
            for run in decision.runs
            if run.candidate_id == candidate.candidate_id
        ]
        for candidate in decision.candidates
    }


def _grades(decision, *, default):
    return {
        candidate.candidate_id: {
            fixture.fixture_id: {
                criterion: default for criterion in decision.criterion_weights
            }
            for fixture in decision.fixtures
        }
        for candidate in decision.candidates
    }


def _operational(decision):
    return {
        candidate.candidate_id: {
            "production_eligible": True,
            "resource_limits_passed": True,
            "total_latency_seconds": "1.000000",
            "total_estimated_cost_usd": "0.01000000",
            "production_integration_delta": candidate.production_delta,
        }
        for candidate in decision.candidates
    }
