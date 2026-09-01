"""Provider-free tests for the pilot-minimal PS1 evidence path."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from app.services.evaluation_data_handling import derive_restricted_trace_reference
from app.services.evaluation_ps1 import (
    Ps1ContractError,
    Ps1EvidenceCandidate,
    Ps1RefetchObservation,
    assemble_ps1_evidence_bundle,
    build_ps1_classifier_input,
    record_ps1_discovery_url,
    verify_ps1_contracts,
)


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "docs" / "testing" / "ai-evaluation"
MANUFACTURER_URL = (
    "https://www.logitech.com/en-us/shop/p/mx-master-3s.910-006557"
)
RETAILER_URL = (
    "https://www.officedepot.com/a/products/2083831/"
    "Logitech-MX-Master-3S-Wireless-Performance/"
)


def _capabilities(count: int, *, offset: int = 1):
    return {
        position: derive_restricted_trace_reference(
            (position + offset).to_bytes(2, "big") * 8
        )
        for position in range(count)
    }


def _classifier(url: str, *, auth: str = "public_unauthenticated"):
    capabilities = _capabilities(1)
    return (
        build_ps1_classifier_input(
            exact_urls=(url,),
            retrieval_auth_contexts=(auth,),
            reference_capabilities=capabilities,
        ),
        capabilities,
    )


def _discovery(url: str, *, ordinal: int = 1):
    return record_ps1_discovery_url(
        candidate_id="openai_unified_premium_v1",
        provider="OpenAI",
        discovery_ordinal=ordinal,
        exact_url=url,
        provider_snippet="untrusted provider prose must not become evidence",
        provider_citation="untrusted-citation",
    )


def _manufacturer_refetch(*, retrieval_attempt_ordinal: int = 1):
    classifier_input, capabilities = _classifier(MANUFACTURER_URL)
    body = (
        "MX Master 3S Graphite standard right-handed mouse. "
        "Includes Logi Bolt USB receiver. Manufacturer list price $119.99 USD."
    )
    return Ps1RefetchObservation(
        discovery=_discovery(MANUFACTURER_URL, ordinal=1),
        retrieval_attempt_ordinal=retrieval_attempt_ordinal,
        tool_call_ordinal=1,
        result_ordinal=1,
        classifier_input=classifier_input,
        reference_capabilities=capabilities,
        status_code=200,
        captured_at=datetime(2026, 8, 31, 18, 0, tzinfo=UTC),
        display_name="Logitech MX Master 3S",
        decoded_body=body,
        evidence_candidates=(
            Ps1EvidenceCandidate("identity", "MX Master 3S Graphite standard right-handed mouse."),
            Ps1EvidenceCandidate("bundle", "Includes Logi Bolt USB receiver."),
            Ps1EvidenceCandidate("price", "Manufacturer list price $119.99 USD."),
            Ps1EvidenceCandidate("regional_context", "Manufacturer list price $119.99 USD."),
        ),
    )


def _retailer_refetch(*, retrieval_attempt_ordinal: int = 1):
    classifier_input, capabilities = _classifier(RETAILER_URL)
    body = (
        "Logitech MX Master 3S Graphite model 910-006556 with Logi Bolt receiver. "
        "Available in the United States for $109.99 USD."
    )
    return Ps1RefetchObservation(
        discovery=_discovery(RETAILER_URL, ordinal=2),
        retrieval_attempt_ordinal=retrieval_attempt_ordinal,
        tool_call_ordinal=1,
        result_ordinal=2,
        classifier_input=classifier_input,
        reference_capabilities=capabilities,
        status_code=200,
        captured_at=datetime(2026, 8, 31, 18, 1, tzinfo=UTC),
        display_name="Office Depot MX Master 3S",
        decoded_body=body,
        evidence_candidates=(
            Ps1EvidenceCandidate(
                "identity",
                "Logitech MX Master 3S Graphite model 910-006556 with Logi Bolt receiver.",
            ),
            Ps1EvidenceCandidate(
                "availability",
                "Available in the United States for $109.99 USD.",
            ),
            Ps1EvidenceCandidate(
                "price",
                "Available in the United States for $109.99 USD.",
            ),
            Ps1EvidenceCandidate(
                "regional_context",
                "Available in the United States for $109.99 USD.",
            ),
        ),
    )


def test_ps1_contract_inventory_is_frozen_and_pilot_scoped():
    contracts = verify_ps1_contracts()

    assert contracts.source_classification.policy_id == "source_classification_policy_v1"
    assert contracts.origin_registry.policy_id == (
        "url_security_operational_origin_rule_registry_v1"
    )
    assert contracts.objective_support.policy_id == (
        "retrieval_objective_support_policy_v1"
    )
    assert contracts.evidence_extractor.policy_id == (
        "deterministic_trace_backed_evidence_extractor_and_matcher_v1"
    )
    assert contracts.origin_registry.rule_count == 2
    assert contracts.objective_support.objective_count == 3
    assert contracts.source_classification.supported_source_types == (
        "manufacturer",
        "established_retailer",
    )
    assert contracts.provider_calls_allowed is False


def test_discovery_is_not_evidence_and_provider_material_cannot_bypass_refetch():
    discovery = _discovery(MANUFACTURER_URL)

    assert discovery.canonical_evidence_eligible is False
    with pytest.raises(Ps1ContractError, match="trace_backed_refetch_required"):
        assemble_ps1_evidence_bundle(
            retrieval_status="completed",
            discoveries=(discovery,),
            refetch_observations=(),
        )


def test_public_safe_refetch_builds_deterministic_schema_valid_bundle():
    manufacturer = _manufacturer_refetch()
    retailer = _retailer_refetch()
    discoveries = (manufacturer.discovery, retailer.discovery)

    first = assemble_ps1_evidence_bundle(
        retrieval_status="completed",
        discoveries=discoveries,
        refetch_observations=(manufacturer, retailer),
    )
    second = assemble_ps1_evidence_bundle(
        retrieval_status="completed",
        discoveries=discoveries,
        refetch_observations=(manufacturer, retailer),
    )

    assert first.canonical_bundle == second.canonical_bundle
    assert first.canonical_evidence_bundle_hash == second.canonical_evidence_bundle_hash
    assert tuple(source["source_id"] for source in first.canonical_bundle["sources"]) == (
        "src-0001",
        "src-0002",
    )
    assert tuple(
        evidence["evidence_id"]
        for source in first.canonical_bundle["sources"]
        for evidence in source["evidence_items"]
    ) == tuple(
        [f"ev-0001-{index:04d}" for index in range(1, 5)]
        + [f"ev-0002-{index:04d}" for index in range(1, 5)]
    )
    assert [item["support"] for item in first.objective_support] == [
        "sufficient",
        "sufficient",
        "sufficient",
    ]
    assert first.canonical_bundle["sources"][0]["source_type"] == "manufacturer"
    assert first.canonical_bundle["sources"][1]["source_type"] == (
        "established_retailer"
    )
    exposed = first.canonical_bundle
    exposed["sources"].clear()
    support = first.objective_support
    support[0]["support"] = "insufficient"
    assert len(first.canonical_bundle["sources"]) == 2
    assert first.objective_support[0]["support"] == "sufficient"
    with pytest.raises(Ps1ContractError, match="assembly_identity"):
        replace(
            first,
            _objective_support_json=json.dumps(
                [{"objective_id": "forged", "support": "sufficient"}]
            ).encode(),
        )


def test_duplicate_discovery_and_refetch_url_deduplicate_to_one_source():
    first = _manufacturer_refetch()
    duplicate = _manufacturer_refetch(retrieval_attempt_ordinal=2)

    result = assemble_ps1_evidence_bundle(
        retrieval_status="partial",
        discoveries=(first.discovery, first.discovery),
        refetch_observations=(first, duplicate),
    )

    assert len(result.canonical_bundle["sources"]) == 1
    assert result.canonical_bundle["sources"][0]["source_id"] == "src-0001"
    assert [item["support"] for item in result.objective_support[:2]] == [
        "sufficient",
        "insufficient",
    ]


def test_explicit_and_implicit_default_https_ports_share_one_source_identity():
    implicit = _manufacturer_refetch()
    explicit_url = MANUFACTURER_URL.replace(
        "https://www.logitech.com/",
        "https://www.logitech.com:443/",
    )
    explicit_classifier, explicit_capabilities = _classifier(explicit_url)
    explicit = replace(
        implicit,
        discovery=_discovery(explicit_url, ordinal=2),
        result_ordinal=2,
        classifier_input=explicit_classifier,
        reference_capabilities=explicit_capabilities,
    )

    result = assemble_ps1_evidence_bundle(
        retrieval_status="partial",
        discoveries=(implicit.discovery, explicit.discovery),
        refetch_observations=(implicit, explicit),
    )

    assert len(result.canonical_bundle["sources"]) == 1
    assert result.canonical_bundle["sources"][0]["url"] == MANUFACTURER_URL


@pytest.mark.parametrize(
    ("url", "auth", "expected"),
    (
        (MANUFACTURER_URL + "?sig=secret", "public_unauthenticated", "signed"),
        (MANUFACTURER_URL, "authenticated", "url_security"),
        ("https://unknown.example/product", "public_unauthenticated", "url_security"),
    ),
)
def test_sensitive_authenticated_and_indeterminate_refetches_fail_closed(
    url,
    auth,
    expected,
):
    classifier_input, capabilities = _classifier(url, auth=auth)
    observation = Ps1RefetchObservation(
        discovery=_discovery(url),
        retrieval_attempt_ordinal=1,
        tool_call_ordinal=1,
        result_ordinal=1,
        classifier_input=classifier_input,
        reference_capabilities=capabilities,
        status_code=200,
        captured_at=datetime(2026, 8, 31, 18, 0, tzinfo=UTC),
        display_name="Unsafe",
        decoded_body="MX Master 3S Graphite",
        evidence_candidates=(Ps1EvidenceCandidate("identity", "MX Master 3S Graphite"),),
    )

    with pytest.raises(Ps1ContractError, match=expected):
        assemble_ps1_evidence_bundle(
            retrieval_status="no_reliable_evidence",
            discoveries=(observation.discovery,),
            refetch_observations=(observation,),
        )


def test_redirect_to_authenticated_destination_fails_closed():
    capabilities = _capabilities(2, offset=5)
    classifier_input = build_ps1_classifier_input(
        exact_urls=(MANUFACTURER_URL, RETAILER_URL),
        retrieval_auth_contexts=("public_unauthenticated", "authenticated"),
        reference_capabilities=capabilities,
    )
    observation = Ps1RefetchObservation(
        discovery=_discovery(MANUFACTURER_URL),
        retrieval_attempt_ordinal=1,
        tool_call_ordinal=1,
        result_ordinal=1,
        classifier_input=classifier_input,
        reference_capabilities=capabilities,
        status_code=200,
        captured_at=datetime(2026, 8, 31, 18, 0, tzinfo=UTC),
        display_name="Redirected",
        decoded_body="MX Master 3S Graphite",
        evidence_candidates=(Ps1EvidenceCandidate("identity", "MX Master 3S Graphite"),),
    )

    with pytest.raises(Ps1ContractError, match="url_security"):
        assemble_ps1_evidence_bundle(
            retrieval_status="no_reliable_evidence",
            discoveries=(observation.discovery,),
            refetch_observations=(observation,),
        )


def test_excerpt_must_be_exactly_trace_backed_and_type_coherent():
    observation = _manufacturer_refetch()
    not_trace_backed = replace(
        observation,
        evidence_candidates=(
            Ps1EvidenceCandidate("identity", "provider summary not in response"),
        ),
    )
    with pytest.raises(Ps1ContractError, match="trace_backed_excerpt"):
        assemble_ps1_evidence_bundle(
            retrieval_status="no_reliable_evidence",
            discoveries=(observation.discovery,),
            refetch_observations=(not_trace_backed,),
        )

    wrong_type = replace(
        observation,
        evidence_candidates=(
            Ps1EvidenceCandidate("price", "Includes Logi Bolt USB receiver."),
        ),
    )
    with pytest.raises(Ps1ContractError, match="evidence_type_coherence"):
        assemble_ps1_evidence_bundle(
            retrieval_status="no_reliable_evidence",
            discoveries=(observation.discovery,),
            refetch_observations=(wrong_type,),
        )


def test_conflict_and_retrieval_status_coherence_are_application_validated():
    retailer = _retailer_refetch()
    body = retailer.decoded_body + " Conflicting variant: MX Master 3S For Mac 910-006570."
    conflicting = replace(
        retailer,
        result_ordinal=1,
        decoded_body=body,
        evidence_candidates=(
            retailer.evidence_candidates
            + (
                Ps1EvidenceCandidate(
                    "identity", "MX Master 3S For Mac 910-006570."
                ),
            )
        ),
    )

    with pytest.raises(Ps1ContractError, match="retrieval_status_coherence"):
        assemble_ps1_evidence_bundle(
            retrieval_status="completed",
            discoveries=(conflicting.discovery,),
            refetch_observations=(conflicting,),
        )


def test_zero_material_objective_manifest_fails_preflight(tmp_path):
    contracts = verify_ps1_contracts()
    artifact = json.loads(
        (ARTIFACTS / "retrieval-objective-support-policy.v1.json").read_text()
    )
    for objective in artifact["ps1_objective_manifest"]["objectives"]:
        objective["materiality"] = "non_material_supporting"
    artifact["specification_identity"]["semantic_hash"] = None
    path = tmp_path / "objective.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")

    with pytest.raises(Ps1ContractError, match="material_objective_set"):
        verify_ps1_contracts(objective_support_path=path)
    assert contracts.objective_support.objective_count == 3


def test_ordinary_projection_excludes_discovery_prose_and_restricted_exact_trace():
    manufacturer = _manufacturer_refetch()
    retailer = _retailer_refetch()
    result = assemble_ps1_evidence_bundle(
        retrieval_status="completed",
        discoveries=(manufacturer.discovery, retailer.discovery),
        refetch_observations=(manufacturer, retailer),
    )

    ordinary = json.dumps(result.ordinary_projection(), sort_keys=True)
    assert "untrusted provider prose" not in ordinary
    assert "untrusted-citation" not in ordinary
    assert "redirect_context" not in ordinary
    assert MANUFACTURER_URL in ordinary
    assert RETAILER_URL in ordinary
    assert len(result.restricted_traces) == 2
    assert all(trace.as_restricted_dict()["exact_url"] for trace in result.restricted_traces)
