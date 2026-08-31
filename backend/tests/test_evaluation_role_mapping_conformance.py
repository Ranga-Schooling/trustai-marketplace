"""Provider-free tests for frozen serialized-placement conformance."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from app.services.evaluation_contract_identity import load_strict_normalization_spec
from app.services.evaluation_role_mapping_conformance import (
    RolePlacementConformanceError,
    validate_serialized_role_placement,
)


SPEC_PATH = (
    Path(__file__).parents[2]
    / "docs"
    / "testing"
    / "ai-evaluation"
    / "normalization-parser.v1.json"
)


def _contract():
    return load_strict_normalization_spec(SPEC_PATH)[
        "provider_role_mapping_contract_v1"
    ]


def _manifest(name):
    return copy.deepcopy(_contract()["request_component_manifests"][name])


def _valid_placement(vector_id):
    vectors = _contract()["conformance_test_vectors"]["vectors"]
    vector = next(item for item in vectors if item["id"] == vector_id)
    return copy.deepcopy(vector["abstract_serialized_placement"])


def _component_bytes(manifest):
    return {
        component["component_id"]: f'<{component["component_id"]}>'.encode()
        for component in manifest["components"]
    }


def _segment_bytes(manifest, placement, component_bytes):
    ordered_ids = [item["component_id"] for item in manifest["components"]]
    final_id = ordered_ids[-1]
    result = {}
    for segment in placement:
        chunks = []
        for component_id in segment["source_component_ids"]:
            chunks.append(component_bytes[component_id])
            if component_id != final_id:
                chunks.append(b"\n")
        result[segment["native_segment_ordinal"]] = b"".join(chunks)
    return result


def _validate(manifest, placement, component_bytes=None, segment_bytes=None):
    if component_bytes is None:
        component_bytes = _component_bytes(manifest)
    if segment_bytes is None:
        segment_bytes = _segment_bytes(
            manifest,
            placement,
            component_bytes,
        )
    return validate_serialized_role_placement(
        manifest=manifest,
        placement=placement,
        component_content_bytes=component_bytes,
        serialized_segment_content_bytes=segment_bytes,
    )


@pytest.mark.parametrize(
    ("manifest_name", "vector_id", "segment_count"),
    (
        ("search_retrieval", "R4", 3),
        ("search_synthesis", "R5", 5),
    ),
)
def test_frozen_mixed_authority_valid_placements_are_derived_as_conformant(
    manifest_name,
    vector_id,
    segment_count,
):
    manifest = _manifest(manifest_name)
    placement = _valid_placement(vector_id)

    assessment = _validate(manifest, placement)

    assert assessment.conformant is True
    assert assessment.preflight_result == "valid"
    assert assessment.component_count == len(manifest["components"])
    assert assessment.segment_count == segment_count
    assert assessment.provider_attempt_created is False
    assert assessment.provider_call_incremented is False
    assert assessment.independently_authorizes_execution is False
    assert assessment.component_grouping == tuple(
        tuple(segment["source_component_ids"]) for segment in placement
    )
    assert assessment.reconstructed_authority_manifest == tuple(
        (item["component_id"], item["authority_class"])
        for item in manifest["components"]
    )


@pytest.mark.parametrize(
    ("manifest_name", "authority", "destination", "violation"),
    (
        (
            "search_retrieval",
            "authoritative_instruction",
            "instruction_surface",
            "mixed_authority_combined",
        ),
        (
            "search_retrieval",
            "untrusted_input",
            "input_surface",
            "mixed_authority_combined",
        ),
        (
            "search_synthesis",
            "authoritative_instruction",
            "instruction_surface",
            "mixed_authority_combined",
        ),
        (
            "search_synthesis",
            "untrusted_input",
            "input_surface",
            "mixed_authority_combined",
        ),
    ),
)
def test_whole_mixed_authority_template_assignment_fails_closed(
    manifest_name,
    authority,
    destination,
    violation,
):
    manifest = _manifest(manifest_name)
    placement = [
        {
            "native_segment_ordinal": 0,
            "source_component_ids": [
                item["component_id"] for item in manifest["components"]
            ],
            "authority_class": authority,
            "native_destination_semantics": destination,
            "content_part_type": "text",
            "ordering_rule": "preserve_source_component_order",
        }
    ]

    with pytest.raises(RolePlacementConformanceError) as caught:
        _validate(manifest, placement)

    assert caught.value.violation == violation
    assert caught.value.provider_attempt_created is False
    assert caught.value.provider_call_incremented is False


@pytest.mark.parametrize(
    ("vector_id", "component_id", "authority", "destination"),
    (
        (
            "R4",
            "search_retrieval_v1_component_2",
            "authoritative_instruction",
            "instruction_surface",
        ),
        (
            "R4",
            "search_retrieval_v1_component_3",
            "untrusted_input",
            "input_surface",
        ),
        (
            "R5",
            "search_synthesis_v1_component_4",
            "authoritative_instruction",
            "instruction_surface",
        ),
        (
            "R5",
            "search_synthesis_v1_component_2",
            "authoritative_instruction",
            "instruction_surface",
        ),
        (
            "R5",
            "search_synthesis_v1_component_4",
            "untrusted_input",
            "input_surface",
        ),
    ),
)
def test_component_authority_promotion_demotion_or_reclassification_fails(
    vector_id,
    component_id,
    authority,
    destination,
):
    manifest_name = "search_retrieval" if vector_id == "R4" else "search_synthesis"
    manifest = _manifest(manifest_name)
    placement = _valid_placement(vector_id)
    target = next(
        segment
        for segment in placement
        if component_id in segment["source_component_ids"]
    )
    target["authority_class"] = authority
    target["native_destination_semantics"] = destination

    with pytest.raises(RolePlacementConformanceError) as caught:
        _validate(manifest, placement)

    assert caught.value.violation == "authority_manifest_reassembly_mismatch"


def test_correct_authority_with_changed_content_or_separator_bytes_fails():
    manifest = _manifest("search_retrieval")
    placement = _valid_placement("R4")
    component_bytes = _component_bytes(manifest)
    segment_bytes = _segment_bytes(manifest, placement, component_bytes)
    segment_bytes[0] += b"changed"

    with pytest.raises(RolePlacementConformanceError) as caught:
        _validate(manifest, placement, component_bytes, segment_bytes)

    assert caught.value.violation == "content_reassembly_mismatch"


@pytest.mark.parametrize("mutation", ("missing", "duplicate", "unknown", "reordered"))
def test_component_coverage_and_canonical_order_are_exact(mutation):
    manifest = _manifest("search_retrieval")
    placement = _valid_placement("R4")
    if mutation == "missing":
        placement[-1]["source_component_ids"].pop()
    elif mutation == "duplicate":
        placement[-1]["source_component_ids"].append(
            placement[-1]["source_component_ids"][-1]
        )
    elif mutation == "unknown":
        placement[-1]["source_component_ids"][-1] = "unknown_component"
    else:
        placement[-1]["source_component_ids"][0:2] = reversed(
            placement[-1]["source_component_ids"][0:2]
        )

    component_bytes = _component_bytes(manifest)
    segment_bytes = {
        segment["native_segment_ordinal"]: b""
        for segment in placement
    }
    with pytest.raises(RolePlacementConformanceError) as caught:
        _validate(manifest, placement, component_bytes, segment_bytes)

    assert caught.value.violation == "source_component_coverage_or_order"


@pytest.mark.parametrize(
    "ordinals",
    (
        [1, 2, 3],
        [0, 2, 3],
        [0, 0, 1],
        [2, 1, 0],
        [False, 1, 2],
        [0.0, 1, 2],
    ),
)
def test_native_segment_ordinals_are_exact_contiguous_in_transmitted_order(
    ordinals,
):
    manifest = _manifest("search_retrieval")
    placement = _valid_placement("R4")
    for segment, ordinal in zip(placement, ordinals, strict=True):
        segment["native_segment_ordinal"] = ordinal

    with pytest.raises(RolePlacementConformanceError) as caught:
        _validate(
            manifest,
            placement,
            _component_bytes(manifest),
            {0: b"", 1: b"", 2: b""},
        )

    assert caught.value.violation == "native_segment_ordinals"


@pytest.mark.parametrize(
    ("field", "value", "violation"),
    (
        ("source_component_ids", "component", "native_segment_shape"),
        ("source_component_ids", [], "native_segment_shape"),
        ("authority_class", "custom", "authority_manifest_reassembly_mismatch"),
        ("native_destination_semantics", "custom", "native_destination_semantics"),
        ("content_part_type", "media", "content_part_type"),
        ("ordering_rule", "other", "ordering_rule"),
        ("split_boundary_rule", "inside_component", "noncanonical_split_boundary"),
    ),
)
def test_native_segment_fields_are_closed_and_exact(field, value, violation):
    manifest = _manifest("search_retrieval")
    placement = _valid_placement("R4")
    placement[0][field] = value

    with pytest.raises(RolePlacementConformanceError) as caught:
        _validate(
            manifest,
            placement,
            _component_bytes(manifest),
            {index: b"" for index in range(len(placement))},
        )

    assert caught.value.violation == violation


@pytest.mark.parametrize("manifest", (None, [], {}, {"components": None}))
def test_manifest_shape_fails_closed(manifest):
    with pytest.raises(RolePlacementConformanceError) as caught:
        validate_serialized_role_placement(
            manifest=manifest,
            placement=[],
            component_content_bytes={},
            serialized_segment_content_bytes={},
        )

    assert caught.value.violation == "component_manifest"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("template_sha256", "not-a-hash"),
        ("template_sha256", ["0" * 64]),
        ("content_identity", "wrong-content-identity"),
        ("authority_class", ["authoritative_instruction"]),
        ("authority_class", "custom"),
        ("content_source", ["frozen_static_canonical_content"]),
        ("content_integrity_rule", ["exact_frozen_component_value"]),
        (
            "content_integrity_rule",
            "exact_canonical_rendered_component_value",
        ),
        ("provider_visibility", ["provider_visible_text"]),
    ),
)
def test_manifest_component_scalar_fields_fail_closed(field, value):
    manifest = _manifest("search_retrieval")
    manifest["components"][0][field] = value

    with pytest.raises(RolePlacementConformanceError) as caught:
        _validate(manifest, _valid_placement("R4"))

    assert caught.value.violation == "component_manifest"


def test_manifest_required_fields_hash_consistency_and_template_blocks_are_exact():
    manifest = _manifest("search_retrieval")
    manifest["components"][0].pop("content_identity")
    with pytest.raises(RolePlacementConformanceError) as caught:
        _validate(manifest, _valid_placement("R4"))
    assert caught.value.violation == "component_manifest"

    manifest = _manifest("search_retrieval")
    changed_hash = "0" * 64
    manifest["components"][1]["template_sha256"] = changed_hash
    manifest["components"][1]["content_identity"] = (
        f"{changed_hash}:canonical_content[1]"
    )
    with pytest.raises(RolePlacementConformanceError) as caught:
        _validate(manifest, _valid_placement("R4"))
    assert caught.value.violation == "component_manifest"

    manifest = _manifest("text_analysis")
    system_hash = manifest["components"][0]["template_sha256"]
    final = manifest["components"][-1]
    final["template_id"] = "text_system_v1"
    final["template_sha256"] = system_hash
    final["component_index"] = 14
    final["content_identity"] = f"{system_hash}:canonical_content[14]"
    with pytest.raises(RolePlacementConformanceError) as caught:
        _validate(manifest, [])
    assert caught.value.violation == "component_manifest"

    manifest = _manifest("search_retrieval")
    manifest["template_sha256"] = "0" * 64
    with pytest.raises(RolePlacementConformanceError) as caught:
        _validate(manifest, _valid_placement("R4"))
    assert caught.value.violation == "component_manifest"


def test_manifest_template_order_and_rendered_source_authority_are_exact():
    manifest = _manifest("text_analysis")
    placement = [
        {
            "native_segment_ordinal": 0,
            "source_component_ids": [
                item["component_id"] for item in manifest["components"][:14]
            ],
            "authority_class": "authoritative_instruction",
            "native_destination_semantics": "instruction_surface",
            "content_part_type": "text",
            "ordering_rule": "preserve_source_component_order",
        },
        {
            "native_segment_ordinal": 1,
            "source_component_ids": [
                item["component_id"] for item in manifest["components"][14:]
            ],
            "authority_class": "untrusted_input",
            "native_destination_semantics": "input_surface",
            "content_part_type": "text",
            "ordering_rule": "preserve_source_component_order",
        },
    ]

    reordered = copy.deepcopy(manifest)
    reordered["ordered_template_ids"].reverse()
    with pytest.raises(RolePlacementConformanceError) as caught:
        _validate(reordered, placement)
    assert caught.value.violation == "component_manifest"

    incoherent = copy.deepcopy(manifest)
    target = next(
        item
        for item in incoherent["components"]
        if item["content_source"] == "rendered_untrusted_listing_data"
    )
    target["authority_class"] = "authoritative_instruction"
    with pytest.raises(RolePlacementConformanceError) as caught:
        _validate(incoherent, placement)
    assert caught.value.violation == "component_manifest"


@pytest.mark.parametrize("placement", (None, [], {}, [None], [{}]))
def test_placement_container_and_required_fields_fail_closed(placement):
    manifest = _manifest("search_retrieval")
    with pytest.raises(RolePlacementConformanceError) as caught:
        validate_serialized_role_placement(
            manifest=manifest,
            placement=placement,
            component_content_bytes=_component_bytes(manifest),
            serialized_segment_content_bytes={},
        )
    assert caught.value.violation == "native_segment_shape"


def test_component_and_segment_byte_inventories_are_exact_and_bytes_only():
    manifest = _manifest("search_retrieval")
    placement = _valid_placement("R4")
    component_bytes = _component_bytes(manifest)
    segment_bytes = _segment_bytes(manifest, placement, component_bytes)

    component_bytes.pop(next(iter(component_bytes)))
    with pytest.raises(RolePlacementConformanceError) as caught:
        _validate(manifest, placement, component_bytes, segment_bytes)
    assert caught.value.violation == "component_content_inventory"

    component_bytes = _component_bytes(manifest)
    component_bytes[next(iter(component_bytes))] = bytearray(b"mutable")
    with pytest.raises(RolePlacementConformanceError) as caught:
        _validate(manifest, placement, component_bytes, segment_bytes)
    assert caught.value.violation == "component_content_bytes"

    component_bytes = _component_bytes(manifest)
    segment_bytes.pop(0)
    with pytest.raises(RolePlacementConformanceError) as caught:
        _validate(manifest, placement, component_bytes, segment_bytes)
    assert caught.value.violation == "serialized_segment_content_inventory"

    with pytest.raises(RolePlacementConformanceError) as caught:
        validate_serialized_role_placement(
            manifest=manifest,
            placement=placement,
            component_content_bytes=component_bytes,
            serialized_segment_content_bytes=None,
        )
    assert caught.value.violation == "serialized_segment_content_inventory"


def test_content_and_separator_corruption_are_independently_detected():
    manifest = _manifest("search_retrieval")
    placement = _valid_placement("R4")
    component_bytes = _component_bytes(manifest)
    segment_bytes = _segment_bytes(manifest, placement, component_bytes)

    segment_bytes[0] = b"X" + segment_bytes[0][1:]
    with pytest.raises(RolePlacementConformanceError) as caught:
        _validate(manifest, placement, component_bytes, segment_bytes)
    assert caught.value.violation == "content_reassembly_mismatch"

    segment_bytes = _segment_bytes(manifest, placement, component_bytes)
    newline = segment_bytes[0].index(b"\n")
    segment_bytes[0] = segment_bytes[0][:newline] + segment_bytes[0][newline + 1 :]
    with pytest.raises(RolePlacementConformanceError) as caught:
        _validate(manifest, placement, component_bytes, segment_bytes)
    assert caught.value.violation == "content_reassembly_mismatch"

    segment_bytes = _segment_bytes(manifest, placement, component_bytes)
    segment_bytes[0] = bytearray(segment_bytes[0])
    with pytest.raises(RolePlacementConformanceError) as caught:
        _validate(manifest, placement, component_bytes, segment_bytes)
    assert caught.value.violation == "serialized_segment_content_bytes"

    segment_bytes = _segment_bytes(manifest, placement, component_bytes)
    segment_bytes[False] = segment_bytes.pop(0)
    with pytest.raises(RolePlacementConformanceError) as caught:
        _validate(manifest, placement, component_bytes, segment_bytes)
    assert caught.value.violation == "serialized_segment_content_inventory"


def test_assessment_is_immutable_and_detached_from_caller_structures():
    manifest = _manifest("search_retrieval")
    placement = _valid_placement("R4")
    assessment = _validate(manifest, placement)
    original = copy.deepcopy(assessment)

    manifest["components"].clear()
    placement.clear()

    assert assessment == original
    with pytest.raises((AttributeError, TypeError)):
        assessment.conformant = False


def test_frozen_structural_vectors_and_execution_boundary_are_preserved():
    contract = _contract()
    conformance = contract["conformance_test_vectors"]
    mixed = contract["mixed_authority_conformance_test_vectors"]

    assert conformance["expected_vector_count"] == 12
    assert len(conformance["vectors"]) == 12
    assert conformance["provider_calls_required"] is False
    assert mixed["expected_vector_count"] == 14
    assert len(mixed["vectors"]) == 14
    assert mixed["provider_calls_required"] is False
    assert contract["independently_authorizes_execution"] is False
    assert contract["future_external_dependency"]["status"] == "pending_creation"
