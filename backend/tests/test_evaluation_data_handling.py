"""Provider-neutral enforcement for the frozen evaluation data boundary."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path

import pytest

from app.services.evaluation_data_handling import (
    DataHandlingPolicyError,
    OrdinaryProviderDataProjection,
    ProviderDataProjections,
    RestrictedProviderDataProjection,
    SafeTransportMetadata,
    authorize_public_safe_url,
    capture_restricted_url_trace,
    derive_restricted_trace_reference,
    evaluate_region_binding,
    evaluate_restricted_retention,
    project_provider_data,
    sanitize_transport_metadata,
    verify_provider_data_handling_artifact,
)
from app.services.evaluation_retrieval_trace import (
    derive_public_safe_deduplication_key,
)


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = (
    ROOT
    / "docs"
    / "testing"
    / "ai-evaluation"
    / "provider-data-handling-review.v1.json"
)
URL_POLICY_PATH = (
    ROOT
    / "docs"
    / "testing"
    / "ai-evaluation"
    / "url-security-policy.v1.json"
)


def _canonical_bytes(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _delete_pointer(document, pointer):
    parent = document
    segments = pointer[1:].split("/")
    for segment in segments[:-1]:
        parent = parent[segment.replace("~1", "/").replace("~0", "~")]
    del parent[segments[-1].replace("~1", "/").replace("~0", "~")]


def _public_safe_trace_and_key():
    trace, classifier_input = _restricted_trace("D7")
    return trace, derive_public_safe_deduplication_key(**classifier_input)


def _restricted_trace(vector_id="D1"):
    artifact = json.loads(URL_POLICY_PATH.read_text(encoding="utf-8"))
    vector = next(
        vector
        for group_name in (
            "existing_direct",
            "existing_redirect",
            "existing_propagation_and_privacy",
            "existing_positive_proof",
            "adversarial",
        )
        for vector in artifact["test_vectors"][group_name]
        if vector["id"] == vector_id
    )
    classifier_input = json.loads(json.dumps(vector["classifier_input"]))
    capabilities = {}
    for member in classifier_input["redirect_context"]["members"]:
        position = member["position"]
        capability = derive_restricted_trace_reference(
            position.to_bytes(2, "big") * 8
        )
        member["restricted_trace_reference"] = capability.value
        capabilities[position] = capability
    current = classifier_input["redirect_context"]["current_position"]
    classifier_input["restricted_trace_reference"] = capabilities[current].value
    return (
        capture_restricted_url_trace(
            classifier_input,
            reference_capabilities=capabilities,
        ),
        classifier_input,
    )


def _valid_safe_metadata():
    return {
        "provider": "synthetic-provider",
        "model": "synthetic-model",
        "model_version_or_snapshot": "synthetic-snapshot",
        "http_or_result_status": {
            "kind": "http_status",
            "value": 200,
        },
        "started_at": "2026-08-31T12:00:00.000Z",
        "completed_at": "2026-08-31T12:00:01.250Z",
        "latency_measurements": {
            "end_to_end_latency_ms": 1250,
            "provider_latency_ms": 1100,
        },
        "input_token_usage": 120,
        "output_token_usage": 45,
        "reasoning_usage_if_exposed": 10,
        "image_usage_if_exposed": 0,
        "finish_or_stop_reason": "accepted",
        "attempt_number": 1,
        "retry_count": 0,
    }


def test_policy_artifact_freezes_governance_boundary_and_identity():
    artifact = verify_provider_data_handling_artifact(POLICY_PATH)

    assert artifact["artifact_id"] == "provider_data_handling_review_v1"
    assert artifact["artifact_version"] == "v1"
    assert artifact["status"] == "frozen"
    assert artifact["provider_neutral"] is True
    assert artifact["retention_policy"]["restricted_retention_days"] == 30
    assert artifact["retention_policy"]["clock_starts_at"] == (
        "final_model_selection_decision_at"
    )
    assert artifact["execution_boundary"] == {
        "authoritative_execution_gate": "experiment.v1.json execution_gate",
        "execution_state": "blocked_pre_execution",
        "provider_calls_allowed": False,
        "pilot_calls_allowed": False,
        "scored_calls_allowed": False,
        "this_artifact_independently_authorizes_execution": False,
    }

    semantic = artifact["specification_identity"]["semantic_identity"]
    content = json.loads(json.dumps(artifact))
    for pointer in semantic["semantic_excluded_json_pointers"]:
        _delete_pointer(content, pointer)
    envelope = {
        "identity_domain": semantic["identity_domain"],
        "policy_id": artifact["artifact_id"],
        "policy_version": artifact["artifact_version"],
        "content": content,
    }
    computed = hashlib.sha256(_canonical_bytes(envelope)).hexdigest()
    assert computed == artifact["specification_identity"]["derived_hash_cache"][
        "policy_semantic_hash"
    ]


@pytest.mark.parametrize(
    ("section", "field", "mutated"),
    [
        ("raw_provider_response_policy", "ordinary_projection_allowed", True),
        ("retention_policy", "restricted_retention_days", 31),
        ("regional_binding", "status", "ready"),
        ("execution_boundary", "provider_calls_allowed", True),
        ("credential_boundary", "credential_hash_in_ordinary_records_allowed", True),
    ],
)
def test_normative_policy_mutations_are_rejected(
    tmp_path,
    section,
    field,
    mutated,
):
    artifact = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    artifact[section][field] = mutated
    path = tmp_path / "mutated-policy.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(DataHandlingPolicyError):
        verify_provider_data_handling_artifact(path)


def test_safe_metadata_allowlist_is_closed_and_exact():
    artifact = verify_provider_data_handling_artifact(POLICY_PATH)
    fields = artifact["safe_transport_metadata"]["field_definitions"]
    assert list(fields) == [
        "provider",
        "model",
        "model_version_or_snapshot",
        "provider_request_id",
        "http_or_result_status",
        "started_at",
        "completed_at",
        "latency_measurements",
        "input_token_usage",
        "output_token_usage",
        "reasoning_usage_if_exposed",
        "image_usage_if_exposed",
        "finish_or_stop_reason",
        "attempt_number",
        "retry_count",
    ]
    assert fields["provider_request_id"]["runtime_acceptance"] == (
        "blocked_until_provider_specific_non_secret_verifier_is_frozen"
    )
    assert artifact["safe_transport_metadata"]["unknown_field_result"] == (
        "excluded_or_failed_closed"
    )


@pytest.mark.parametrize(
    "field",
    [
        "authorization",
        "Authorization",
        "cookie",
        "set_cookie",
        "signed_url",
        "api_key",
        "session_identifier",
        "arbitrary_metadata",
        "provider_diagnostic_prose",
        "raw_tool_arguments",
        "raw_response_fragment",
        "private_url",
        "authentication_token",
    ],
)
def test_unknown_or_forbidden_transport_metadata_is_denied(field):
    with pytest.raises(DataHandlingPolicyError, match="metadata_field_not_allowed"):
        sanitize_transport_metadata({field: "synthetic-non-secret"})


def test_provider_request_id_is_denied_until_local_verifier_is_frozen():
    with pytest.raises(
        DataHandlingPolicyError,
        match="provider_request_id_verifier_not_frozen",
    ):
        sanitize_transport_metadata({"provider_request_id": "synthetic-request"})


def test_safe_timing_usage_finish_and_counters_are_accepted_and_immutable():
    source = _valid_safe_metadata()
    safe = sanitize_transport_metadata(source)
    before = safe.as_dict()

    source["latency_measurements"]["end_to_end_latency_ms"] = 999999
    source["input_token_usage"] = 999999

    assert safe.as_dict() == before
    assert safe.as_dict()["latency_measurements"]["end_to_end_latency_ms"] == 1250
    with pytest.raises(FrozenInstanceError):
        safe.values = ()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider", 7),
        ("model", ""),
        ("input_token_usage", True),
        ("output_token_usage", -1),
        ("retry_count", 1.5),
        ("finish_or_stop_reason", "provider supplied prose"),
        ("started_at", "yesterday"),
        ("latency_measurements", {"provider_latency_ms": -1}),
        ("latency_measurements", {"unknown_latency_ms": 1}),
        ("http_or_result_status", {"kind": "http_status", "value": 99}),
    ],
)
def test_malformed_safe_metadata_type_is_denied(field, value):
    with pytest.raises(DataHandlingPolicyError):
        sanitize_transport_metadata({field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider", "synthetic provider"),
        ("model", "synthetic\nmodel"),
        ("model_version_or_snapshot", "token=SYNTHETIC-NON-SECRET"),
        ("finish_or_stop_reason", "synthetic_provider_finish"),
    ],
)
def test_identifier_and_finish_fields_do_not_accept_arbitrary_text(field, value):
    with pytest.raises(DataHandlingPolicyError):
        sanitize_transport_metadata({field: value})


def test_status_object_key_order_is_not_semantically_significant():
    safe = sanitize_transport_metadata(
        {"http_or_result_status": {"value": 200, "kind": "http_status"}}
    )
    assert safe.as_dict() == {
        "http_or_result_status": {"kind": "http_status", "value": 200}
    }


def test_nested_restricted_material_cannot_bypass_top_level_allowlist():
    with pytest.raises(DataHandlingPolicyError, match="metadata_field_not_allowed"):
        sanitize_transport_metadata(
            {
                "latency_measurements": {
                    "provider_latency_ms": 12,
                    "authorization": "synthetic-non-secret",
                }
            }
        )


def test_raw_response_and_exact_urls_are_restricted_only_and_hash_is_ordinary():
    raw = b'{"synthetic":"provider output"}'
    trace, classifier_input = _restricted_trace()
    projections = project_provider_data(
        raw_provider_response=raw,
        restricted_url_trace=trace,
        safe_transport_metadata=_valid_safe_metadata(),
    )

    ordinary = projections.ordinary.as_dict()
    restricted = projections.restricted.as_dict()
    assert ordinary["raw_provider_response_hash"] == hashlib.sha256(raw).hexdigest()
    assert ordinary["restricted_trace_reference"] == (
        classifier_input["restricted_trace_reference"]
    )
    assert "raw_provider_response" not in ordinary
    assert "exact_url_traces" not in ordinary
    assert restricted["raw_provider_response"] == raw
    assert restricted["exact_url_traces"] == (classifier_input,)


def test_public_safe_url_requires_frozen_downstream_permission():
    trace, key = _public_safe_trace_and_key()
    with pytest.raises(DataHandlingPolicyError, match="downstream_url_disclosure"):
        authorize_public_safe_url(key, downstream_contract_id="grader_package_v1")

    disclosure = authorize_public_safe_url(
        key,
        downstream_contract_id="retrieval_evidence_bundle_v1",
    )
    projections = project_provider_data(
        raw_provider_response=None,
        restricted_url_trace=trace,
        safe_transport_metadata={},
        public_safe_url_disclosures=(disclosure,),
    )
    assert projections.ordinary.as_dict()["public_safe_canonical_urls"] == (
        key.safe_canonical_url,
    )


def test_restricted_url_hash_cannot_enter_ordinary_projection():
    with pytest.raises(DataHandlingPolicyError, match="restricted_url_hash"):
        project_provider_data(
            raw_provider_response=None,
            restricted_url_trace=None,
            safe_transport_metadata={},
            ordinary_hashes={"restricted_url_hash": "0" * 64},
        )


def test_ordinary_projection_rejects_credential_material():
    with pytest.raises(DataHandlingPolicyError, match="credential_material"):
        project_provider_data(
            raw_provider_response=None,
            restricted_url_trace=None,
            safe_transport_metadata={},
            credential_material={"api_key": "synthetic-non-secret"},
        )


def test_restricted_transport_metadata_requires_later_explicit_binding():
    with pytest.raises(DataHandlingPolicyError, match="restricted_metadata_binding"):
        project_provider_data(
            raw_provider_response=None,
            restricted_url_trace=None,
            safe_transport_metadata={},
            restricted_transport_metadata={"diagnostic": "synthetic"},
        )


def test_restricted_projection_is_immutable_against_caller_mutation():
    trace, classifier_input = _restricted_trace()
    projections = project_provider_data(
        raw_provider_response=b"raw",
        restricted_url_trace=trace,
        safe_transport_metadata={},
    )
    classifier_input["exact_url"] = "https://changed.example/"
    assert projections.restricted.as_dict()["exact_url_traces"] == (
        trace.as_restricted_dict(),
    )
    with pytest.raises(FrozenInstanceError):
        projections.restricted.raw_provider_response = b"changed"


def test_projection_value_objects_cannot_bypass_validating_factories():
    with pytest.raises(DataHandlingPolicyError, match="factory_required"):
        SafeTransportMetadata((("authorization", "synthetic"),))
    with pytest.raises(DataHandlingPolicyError, match="factory_required"):
        OrdinaryProviderDataProjection(None, None, (), object())
    with pytest.raises(DataHandlingPolicyError, match="factory_required"):
        RestrictedProviderDataProjection(b"secret", (), (), ())
    with pytest.raises(DataHandlingPolicyError, match="factory_required"):
        ProviderDataProjections(object(), object())


def test_restricted_trace_reference_is_opaque_random_and_url_independent():
    reference = derive_restricted_trace_reference(bytes(range(16)))
    assert reference.value == "rtr-v1-000102030405060708090a0b0c0d0e0f"
    assert len(reference.value) == 39
    with pytest.raises(DataHandlingPolicyError, match="restricted_trace_entropy"):
        derive_restricted_trace_reference(b"short")


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (timedelta(seconds=-1), "retained"),
        (timedelta(0), "deletion_due"),
        (timedelta(seconds=1), "deletion_overdue"),
    ],
)
def test_restricted_retention_relative_to_final_decision(offset, expected):
    decision = datetime(2026, 8, 1, tzinfo=UTC)
    state = evaluate_restricted_retention(
        final_model_selection_decision_at=decision,
        observed_at=decision + timedelta(days=30) + offset,
    )
    assert state.state == expected
    assert state.expires_at == decision + timedelta(days=30)
    assert state.deletion_schedule_resolved is True
    assert state.deletion_required is (expected != "retained")


def test_retention_without_final_selection_decision_is_blocking():
    state = evaluate_restricted_retention(
        final_model_selection_decision_at=None,
        observed_at=datetime(2026, 8, 31, tzinfo=UTC),
    )
    assert state.state == "blocked_pending_final_model_selection_decision"
    assert state.expires_at is None
    assert state.deletion_schedule_resolved is False
    assert state.deletion_required is False


def test_restricted_lifecycle_group_rejects_partial_deletion():
    decision = datetime(2026, 8, 1, tzinfo=UTC)
    with pytest.raises(DataHandlingPolicyError, match="partial_lifecycle_deletion"):
        evaluate_restricted_retention(
            final_model_selection_decision_at=decision,
            observed_at=decision + timedelta(days=31),
            lifecycle_member_deletion_states={
                "raw_provider_response": "deleted",
                "exact_url_traces": "retained",
                "restricted_transport_metadata": "deleted",
                "restricted_linkage_material": "deleted",
            },
        )


def test_restricted_lifecycle_group_requires_complete_member_inventory():
    decision = datetime(2026, 8, 1, tzinfo=UTC)
    with pytest.raises(DataHandlingPolicyError, match="lifecycle_member_inventory"):
        evaluate_restricted_retention(
            final_model_selection_decision_at=decision,
            observed_at=decision + timedelta(days=31),
            lifecycle_member_deletion_states={
                "raw_provider_response": "deleted",
            },
        )


def test_unresolved_region_is_a_pre_execution_blocker():
    unresolved = evaluate_region_binding(
        approved_execution_region=None,
        restricted_storage_region=None,
    )
    assert unresolved.state == "blocked_pending_region_binding"
    assert unresolved.pre_execution_ready is False

    ready = evaluate_region_binding(
        approved_execution_region="synthetic-region-1",
        restricted_storage_region="synthetic-region-1",
    )
    assert ready.state == "ready"
    assert ready.pre_execution_ready is True

    mismatch = evaluate_region_binding(
        approved_execution_region="synthetic-region-1",
        restricted_storage_region="synthetic-region-2",
    )
    assert mismatch.state == "blocked_region_mismatch"
    assert mismatch.pre_execution_ready is False
