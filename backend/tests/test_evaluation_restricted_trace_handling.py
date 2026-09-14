"""Restricted retrieval-trace capture at the frozen privacy boundary."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest

from app.services.evaluation_data_handling import (
    DataHandlingPolicyError,
    RestrictedUrlTrace,
    authorize_public_safe_url,
    capture_restricted_url_trace,
    derive_restricted_trace_reference,
    project_provider_data,
)
from app.services.evaluation_retrieval_trace import (
    derive_public_safe_deduplication_key,
)


ROOT = Path(__file__).resolve().parents[2]
URL_POLICY_PATH = (
    ROOT
    / "docs"
    / "testing"
    / "ai-evaluation"
    / "url-security-policy.v1.json"
)
URL_POLICY = json.loads(URL_POLICY_PATH.read_text(encoding="utf-8"))


def _classifier_case(vector_id):
    vector = next(
        vector
        for group_name in (
            "existing_direct",
            "existing_redirect",
            "existing_propagation_and_privacy",
            "existing_positive_proof",
            "adversarial",
        )
        for vector in URL_POLICY["test_vectors"][group_name]
        if vector["id"] == vector_id
    )
    classifier_input = deepcopy(vector["classifier_input"])
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
    return classifier_input, capabilities, vector["expected"]


def test_complete_redirect_trace_is_captured_with_exact_relationship_and_safe_result():
    classifier_input, capabilities, expected = _classifier_case("R2")
    trace = capture_restricted_url_trace(
        classifier_input,
        reference_capabilities=capabilities,
    )

    restricted = trace.as_restricted_dict()
    safe = trace.as_safe_result_dict()
    assert restricted == classifier_input
    assert tuple(
        member["position"]
        for member in restricted["redirect_context"]["members"]
    ) == tuple(range(len(restricted["redirect_context"]["members"])))
    assert safe["classification"] == expected["classification"]
    assert safe["reason_codes"] == expected["reason_codes"]
    assert safe["restricted_trace_reference"] == (
        classifier_input["restricted_trace_reference"]
    )
    assert set(safe) == {
        "classification",
        "reason_codes",
        "url_role",
        "restricted_trace_reference",
        "policy_id",
        "policy_version",
        "policy_hash",
    }
    assert "exact_url" not in safe
    assert "redirect_context" not in safe


def test_restricted_trace_is_deeply_immutable_against_caller_mutation():
    classifier_input, capabilities, _ = _classifier_case("R1")
    trace = capture_restricted_url_trace(
        classifier_input,
        reference_capabilities=capabilities,
    )
    before = trace.as_restricted_dict()

    classifier_input["exact_url"] = "https://changed.invalid/"
    classifier_input["redirect_context"]["members"][0]["exact_url"] = (
        "https://changed.invalid/"
    )
    capabilities.clear()

    assert trace.as_restricted_dict() == before
    with pytest.raises(FrozenInstanceError):
        trace.restricted_input = ()


def test_direct_restricted_trace_construction_cannot_bypass_validation():
    with pytest.raises(DataHandlingPolicyError, match="factory_required"):
        RestrictedUrlTrace((), ())


def test_missing_or_mismatched_reference_capability_is_rejected():
    classifier_input, capabilities, _ = _classifier_case("R2")
    missing = dict(capabilities)
    del missing[0]
    with pytest.raises(DataHandlingPolicyError, match="reference_inventory"):
        capture_restricted_url_trace(
            classifier_input,
            reference_capabilities=missing,
        )

    mismatched = dict(capabilities)
    mismatched[0] = derive_restricted_trace_reference(b"z" * 16)
    with pytest.raises(DataHandlingPolicyError, match="reference_mismatch"):
        capture_restricted_url_trace(
            classifier_input,
            reference_capabilities=mismatched,
        )


def test_capture_rejects_implicit_fields_and_incomplete_member_shape():
    classifier_input, capabilities, _ = _classifier_case("R2")
    classifier_input["extra"] = "not-allowed"
    with pytest.raises(DataHandlingPolicyError, match="classifier_input_keys"):
        capture_restricted_url_trace(
            classifier_input,
            reference_capabilities=capabilities,
        )

    classifier_input, capabilities, _ = _classifier_case("R2")
    del classifier_input["redirect_context"]["members"][0]["origin_rule"]
    with pytest.raises(DataHandlingPolicyError, match="redirect_member_keys"):
        capture_restricted_url_trace(
            classifier_input,
            reference_capabilities=capabilities,
        )


def test_provider_data_projection_keeps_structured_trace_restricted():
    classifier_input, capabilities, _ = _classifier_case("R2")
    trace = capture_restricted_url_trace(
        classifier_input,
        reference_capabilities=capabilities,
    )
    projections = project_provider_data(
        raw_provider_response=b"synthetic raw response",
        restricted_url_trace=trace,
        safe_transport_metadata={"provider": "synthetic-provider"},
    )

    ordinary = projections.ordinary.as_dict()
    restricted = projections.restricted.as_dict()
    assert ordinary["restricted_trace_reference"] == (
        trace.as_safe_result_dict()["restricted_trace_reference"]
    )
    assert "exact_url_traces" not in ordinary
    assert restricted["exact_url_traces"] == (trace.as_restricted_dict(),)
    serialized_ordinary = json.dumps(ordinary)
    assert classifier_input["exact_url"] not in serialized_ordinary
    for member in classifier_input["redirect_context"]["members"]:
        assert member["exact_url"] not in serialized_ordinary


def test_restricted_trace_and_projection_representations_do_not_disclose_content():
    classifier_input, capabilities, _ = _classifier_case("R2")
    trace = capture_restricted_url_trace(
        classifier_input,
        reference_capabilities=capabilities,
    )
    raw = b"synthetic restricted response body"
    projections = project_provider_data(
        raw_provider_response=raw,
        restricted_url_trace=trace,
        safe_transport_metadata={},
    )

    for rendered in (repr(trace), repr(projections.restricted), repr(projections)):
        assert raw.decode() not in rendered
        assert classifier_input["exact_url"] not in rendered
        for member in classifier_input["redirect_context"]["members"]:
            assert member["exact_url"] not in rendered


def test_public_safe_trace_still_remains_restricted_as_exact_trace():
    classifier_input, capabilities, expected = _classifier_case("D7")
    trace = capture_restricted_url_trace(
        classifier_input,
        reference_capabilities=capabilities,
    )
    assert expected["classification"] == "public_safe"
    assert trace.as_safe_result_dict()["classification"] == "public_safe"

    projections = project_provider_data(
        raw_provider_response=None,
        restricted_url_trace=trace,
        safe_transport_metadata={},
    )
    assert projections.ordinary.as_dict()["public_safe_canonical_urls"] == ()
    assert projections.restricted.as_dict()["exact_url_traces"] == (
        trace.as_restricted_dict(),
    )


def test_public_url_disclosure_must_be_bound_to_same_public_safe_final_trace():
    public_input, public_capabilities, _ = _classifier_case("D7")
    public_trace = capture_restricted_url_trace(
        public_input,
        reference_capabilities=public_capabilities,
    )
    public_key = derive_public_safe_deduplication_key(**public_input)
    disclosure = authorize_public_safe_url(
        public_key,
        downstream_contract_id="retrieval_evidence_bundle_v1",
    )
    projections = project_provider_data(
        raw_provider_response=None,
        restricted_url_trace=public_trace,
        safe_transport_metadata={},
        public_safe_url_disclosures=(disclosure,),
    )
    assert projections.ordinary.as_dict()["public_safe_canonical_urls"] == (
        public_input["exact_url"],
    )

    sensitive_input, sensitive_capabilities, _ = _classifier_case("R2")
    sensitive_trace = capture_restricted_url_trace(
        sensitive_input,
        reference_capabilities=sensitive_capabilities,
    )
    with pytest.raises(DataHandlingPolicyError, match="public_url_trace_binding"):
        project_provider_data(
            raw_provider_response=None,
            restricted_url_trace=sensitive_trace,
            safe_transport_metadata={},
            public_safe_url_disclosures=(disclosure,),
        )


def test_public_url_disclosure_without_restricted_trace_is_rejected():
    classifier_input, _, _ = _classifier_case("D7")
    key = derive_public_safe_deduplication_key(**classifier_input)
    disclosure = authorize_public_safe_url(
        key,
        downstream_contract_id="retrieval_evidence_bundle_v1",
    )
    with pytest.raises(DataHandlingPolicyError, match="public_url_trace_binding"):
        project_provider_data(
            raw_provider_response=None,
            restricted_url_trace=None,
            safe_transport_metadata={},
            public_safe_url_disclosures=(disclosure,),
        )


def test_url_policy_classification_mutation_is_not_trusted():
    classifier_input, capabilities, _ = _classifier_case("R2")
    trace = capture_restricted_url_trace(
        classifier_input,
        reference_capabilities=capabilities,
    )
    safe = trace.as_safe_result_dict()
    safe["classification"] = "public_safe"
    safe["reason_codes"] = ()

    assert trace.as_safe_result_dict()["classification"] == "sensitive"
    assert trace.as_safe_result_dict()["reason_codes"]
