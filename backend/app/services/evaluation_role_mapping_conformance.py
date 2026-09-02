"""Provider-neutral serialized-placement conformance checks.

The validator derives structural and byte-level conformance from a frozen
component manifest plus an observed abstract placement.  It intentionally
knows no provider-native field names and cannot select a mapping, construct a
request, create an attempt, increment a call counter, or authorize execution.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any


_AUTHORITY_CLASSES = frozenset(
    {
        "authoritative_instruction",
        "untrusted_input",
        "untrusted_context",
        "untrusted_retrieved_evidence",
        "visual_media",
    }
)
_DESTINATION_SEMANTICS = frozenset(
    {
        "instruction_surface",
        "input_surface",
        "retrieved_evidence_surface",
        "context_surface",
        "media_surface",
    }
)
_AUTHORITY_DESTINATION = {
    "authoritative_instruction": "instruction_surface",
    "untrusted_input": "input_surface",
    "untrusted_context": "context_surface",
    "untrusted_retrieved_evidence": "retrieved_evidence_surface",
    "visual_media": "media_surface",
}
_COMPONENT_REQUIRED_FIELDS = frozenset(
    {
        "component_id",
        "template_id",
        "template_sha256",
        "component_index",
        "authority_class",
        "content_source",
        "content_identity",
        "ordering_index",
        "split_boundary_rule",
        "provider_visibility",
        "content_integrity_rule",
    }
)
_CONTENT_SOURCES = frozenset(
    {
        "frozen_static_canonical_content",
        "rendered_untrusted_listing_data",
        "rendered_untrusted_target_data",
        "rendered_untrusted_retrieved_evidence",
        "rendered_untrusted_visual_context",
    }
)
_CONTENT_INTEGRITY_RULES = frozenset(
    {
        "exact_frozen_component_value",
        "exact_canonical_rendered_component_value",
    }
)
_RENDERED_SOURCE_CONTRACT = {
    "rendered_untrusted_listing_data": (
        "untrusted_input",
        "exact_canonical_rendered_component_value",
    ),
    "rendered_untrusted_target_data": (
        "untrusted_input",
        "exact_canonical_rendered_component_value",
    ),
    "rendered_untrusted_retrieved_evidence": (
        "untrusted_retrieved_evidence",
        "exact_canonical_rendered_component_value",
    ),
    "rendered_untrusted_visual_context": (
        "untrusted_context",
        "exact_canonical_rendered_component_value",
    ),
}
_SEGMENT_REQUIRED_FIELDS = frozenset(
    {
        "native_segment_ordinal",
        "source_component_ids",
        "authority_class",
        "native_destination_semantics",
        "content_part_type",
        "ordering_rule",
    }
)
_LOWER_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RolePlacementConformanceError(ValueError):
    """A placement fails the frozen topology preflight contract."""

    provider_attempt_created = False
    provider_call_incremented = False

    def __init__(self, violation: str) -> None:
        self.violation = violation
        super().__init__(f"topology_preflight_failure:{violation}")


@dataclass(frozen=True)
class RolePlacementAssessment:
    """Immutable evidence that the supplied abstract placement conforms."""

    conformant: bool
    preflight_result: str
    component_count: int
    segment_count: int
    component_grouping: tuple[tuple[str, ...], ...]
    reconstructed_authority_manifest: tuple[tuple[str, str], ...]
    provider_attempt_created: bool = False
    provider_call_incremented: bool = False
    independently_authorizes_execution: bool = False


def _validate_component_manifest(manifest: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(manifest, Mapping):
        raise RolePlacementConformanceError("component_manifest")
    ordered_template_ids = manifest.get("ordered_template_ids")
    components = manifest.get("components")
    if (
        type(ordered_template_ids) is not list
        or not ordered_template_ids
        or any(type(item) is not str or not item for item in ordered_template_ids)
        or len(set(ordered_template_ids)) != len(ordered_template_ids)
        or type(components) is not list
        or not components
    ):
        raise RolePlacementConformanceError("component_manifest")

    validated: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    template_indices: dict[str, list[int]] = {}
    template_hashes: dict[str, str] = {}
    encountered_templates: list[str] = []
    for expected_order, component in enumerate(components):
        required_fields_present = isinstance(
            component,
            Mapping,
        ) and _COMPONENT_REQUIRED_FIELDS.issubset(component)
        if not required_fields_present:
            raise RolePlacementConformanceError("component_manifest")
        component_id = component.get("component_id")
        template_id = component.get("template_id")
        component_index = component.get("component_index")
        ordering_index = component.get("ordering_index")
        template_sha256 = component.get("template_sha256")
        authority_class = component.get("authority_class")
        content_source = component.get("content_source")
        content_identity = component.get("content_identity")
        content_integrity_rule = component.get("content_integrity_rule")
        split_boundary_rule = component.get("split_boundary_rule")
        provider_visibility = component.get("provider_visibility")
        if (
            type(component_id) is not str
            or not component_id
            or component_id in seen_ids
            or type(template_id) is not str
            or not template_id
            or type(component_index) is not int
            or component_index < 0
            or type(ordering_index) is not int
            or ordering_index != expected_order
            or type(template_sha256) is not str
            or _LOWER_SHA256.fullmatch(template_sha256) is None
            or type(content_identity) is not str
            or not content_identity
            or type(authority_class) is not str
            or type(content_source) is not str
            or type(content_integrity_rule) is not str
            or type(split_boundary_rule) is not str
            or type(provider_visibility) is not str
        ):
            raise RolePlacementConformanceError("component_manifest")
        if (
            authority_class not in _AUTHORITY_CLASSES
            or content_source not in _CONTENT_SOURCES
            or split_boundary_rule != "canonical_component_boundary_only"
            or provider_visibility != "provider_visible_text"
            or content_integrity_rule not in _CONTENT_INTEGRITY_RULES
        ):
            raise RolePlacementConformanceError("component_manifest")
        expected_rendered_contract = _RENDERED_SOURCE_CONTRACT.get(content_source)
        if expected_rendered_contract is not None and (
            authority_class,
            content_integrity_rule,
        ) != expected_rendered_contract:
            raise RolePlacementConformanceError("component_manifest")
        if content_source == "frozen_static_canonical_content" and (
            content_integrity_rule != "exact_frozen_component_value"
        ):
            raise RolePlacementConformanceError("component_manifest")
        expected_content_identity = (
            f"{template_sha256}:canonical_content[{component_index}]"
        )
        if content_source != "frozen_static_canonical_content":
            expected_content_identity += f":{content_source}"
        if content_identity != expected_content_identity:
            raise RolePlacementConformanceError("component_manifest")
        previous_hash = template_hashes.setdefault(template_id, template_sha256)
        if previous_hash != template_sha256:
            raise RolePlacementConformanceError("component_manifest")
        if not encountered_templates or encountered_templates[-1] != template_id:
            if template_id in encountered_templates:
                raise RolePlacementConformanceError("component_manifest")
            encountered_templates.append(template_id)
        seen_ids.add(component_id)
        template_indices.setdefault(template_id, []).append(component_index)
        validated.append(dict(component))

    if (
        encountered_templates != ordered_template_ids
        or any(
            indices != list(range(len(indices)))
            for indices in template_indices.values()
        )
    ):
        raise RolePlacementConformanceError("component_manifest")
    top_level_hash = manifest.get("template_sha256")
    if top_level_hash is not None and (
        len(template_hashes) != 1
        or type(top_level_hash) is not str
        or top_level_hash != next(iter(template_hashes.values()))
    ):
        raise RolePlacementConformanceError("component_manifest")
    return tuple(validated)


def _validate_placement_shape(placement: Any) -> tuple[dict[str, Any], ...]:
    if type(placement) is not list or not placement:
        raise RolePlacementConformanceError("native_segment_shape")
    validated: list[dict[str, Any]] = []
    for expected_ordinal, segment in enumerate(placement):
        if not isinstance(segment, Mapping) or not _SEGMENT_REQUIRED_FIELDS.issubset(
            segment
        ):
            raise RolePlacementConformanceError("native_segment_shape")
        ordinal = segment.get("native_segment_ordinal")
        if type(ordinal) is not int or ordinal != expected_ordinal:
            raise RolePlacementConformanceError("native_segment_ordinals")
        source_ids = segment.get("source_component_ids")
        authority_class = segment.get("authority_class")
        destination_semantics = segment.get("native_destination_semantics")
        content_part_type = segment.get("content_part_type")
        ordering_rule = segment.get("ordering_rule")
        split_boundary_rule = segment.get(
            "split_boundary_rule",
            "canonical_component_boundary_only",
        )
        if (
            type(source_ids) is not list
            or not source_ids
            or any(type(item) is not str or not item for item in source_ids)
            or type(authority_class) is not str
            or type(destination_semantics) is not str
            or type(content_part_type) is not str
            or type(ordering_rule) is not str
            or type(split_boundary_rule) is not str
        ):
            raise RolePlacementConformanceError("native_segment_shape")
        if split_boundary_rule != "canonical_component_boundary_only":
            raise RolePlacementConformanceError("noncanonical_split_boundary")
        if destination_semantics not in _DESTINATION_SEMANTICS:
            raise RolePlacementConformanceError("native_destination_semantics")
        if content_part_type != "text":
            raise RolePlacementConformanceError("content_part_type")
        if ordering_rule != "preserve_source_component_order":
            raise RolePlacementConformanceError("ordering_rule")
        validated.append(dict(segment))
    return tuple(validated)


def _require_byte_inventory(
    value: Any,
    expected_keys: tuple[Any, ...],
    inventory_error: str,
    bytes_error: str,
) -> Mapping[Any, bytes]:
    if not isinstance(value, Mapping):
        raise RolePlacementConformanceError(inventory_error)
    expected_key_type = type(expected_keys[0])
    if (
        len(value) != len(expected_keys)
        or any(type(key) is not expected_key_type for key in value)
        or set(value) != set(expected_keys)
    ):
        raise RolePlacementConformanceError(inventory_error)
    if any(type(value[key]) is not bytes for key in expected_keys):
        raise RolePlacementConformanceError(bytes_error)
    return value


def _segment_content_matches(
    actual: bytes,
    source_ids: list[str],
    component_bytes: Mapping[str, bytes],
    final_component_id: str,
) -> bool:
    view = memoryview(actual)
    offset = 0
    for component_id in source_ids:
        content = component_bytes[component_id]
        end = offset + len(content)
        if end > len(view) or view[offset:end] != content:
            return False
        offset = end
        if component_id != final_component_id:
            if offset >= len(view) or view[offset] != 0x0A:
                return False
            offset += 1
    return offset == len(view)


def validate_serialized_role_placement(
    *,
    manifest: Mapping[str, Any],
    placement: list[Mapping[str, Any]],
    component_content_bytes: Mapping[str, bytes],
    serialized_segment_content_bytes: Mapping[int, bytes],
) -> RolePlacementAssessment:
    """Derive frozen structural, authority, and byte-reassembly conformance."""
    components = _validate_component_manifest(manifest)
    segments = _validate_placement_shape(placement)
    ordered_ids = tuple(component["component_id"] for component in components)
    component_by_id = {
        component["component_id"]: component for component in components
    }
    flattened_ids = tuple(
        component_id
        for segment in segments
        for component_id in segment["source_component_ids"]
    )
    if flattened_ids != ordered_ids:
        raise RolePlacementConformanceError(
            "source_component_coverage_or_order"
        )

    component_bytes = _require_byte_inventory(
        component_content_bytes,
        ordered_ids,
        "component_content_inventory",
        "component_content_bytes",
    )
    segment_ordinals = tuple(range(len(segments)))
    segment_bytes = _require_byte_inventory(
        serialized_segment_content_bytes,
        segment_ordinals,
        "serialized_segment_content_inventory",
        "serialized_segment_content_bytes",
    )

    reconstructed: list[tuple[str, str]] = []
    for segment in segments:
        source_ids = segment["source_component_ids"]
        source_authorities = {
            component_by_id[component_id]["authority_class"]
            for component_id in source_ids
        }
        if len(source_authorities) != 1:
            raise RolePlacementConformanceError("mixed_authority_combined")
        expected_authority = next(iter(source_authorities))
        actual_authority = segment.get("authority_class")
        expected_destination = _AUTHORITY_DESTINATION[expected_authority]
        if (
            actual_authority != expected_authority
            or segment["native_destination_semantics"] != expected_destination
        ):
            raise RolePlacementConformanceError(
                "authority_manifest_reassembly_mismatch"
            )
        reconstructed.extend(
            (component_id, actual_authority) for component_id in source_ids
        )
        ordinal = segment["native_segment_ordinal"]
        if not _segment_content_matches(
            segment_bytes[ordinal],
            source_ids,
            component_bytes,
            ordered_ids[-1],
        ):
            raise RolePlacementConformanceError("content_reassembly_mismatch")

    return RolePlacementAssessment(
        conformant=True,
        preflight_result="valid",
        component_count=len(components),
        segment_count=len(segments),
        component_grouping=tuple(
            tuple(segment["source_component_ids"]) for segment in segments
        ),
        reconstructed_authority_manifest=tuple(reconstructed),
    )
