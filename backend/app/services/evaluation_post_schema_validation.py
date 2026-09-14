"""Typed, non-final integration for frozen post-schema validators."""

from __future__ import annotations

from typing import Any

from app.services.evaluation_schema_validation import (
    CanonicalOutputSchemaRegistry,
    CanonicalSchemaValidationError,
    SchemaContractError,
    SchemaValidatedCandidate,
)
from app.services.evaluation_validators import (
    validate_text_cross_fields,
    validate_visual_photo_references,
)


def _detached_payload_for_schema(
    candidate: SchemaValidatedCandidate,
    *,
    expected_schema_id: str,
    schema_registry: CanonicalOutputSchemaRegistry,
) -> dict[str, Any]:
    if type(candidate) is not SchemaValidatedCandidate:
        raise TypeError("candidate must be a SchemaValidatedCandidate")
    if type(schema_registry) is not CanonicalOutputSchemaRegistry:
        raise TypeError("schema_registry must be a CanonicalOutputSchemaRegistry")
    if candidate.schema_id != expected_schema_id:
        raise SchemaContractError("post_schema_candidate_binding")
    try:
        rebound = schema_registry.validate(
            expected_schema_id,
            candidate.canonical_semantic_json,
        )
    except CanonicalSchemaValidationError as exc:
        raise SchemaContractError("post_schema_candidate_validation") from exc
    if (
        candidate.schema_sha256 != rebound.schema_sha256
        or candidate.schema_set_sha256 != rebound.schema_set_sha256
    ):
        raise SchemaContractError("post_schema_candidate_binding")
    payload = rebound.canonical_semantic_json.admitted.value
    if type(payload) is not dict:
        raise SchemaContractError("post_schema_candidate_payload")
    return payload


def validate_text_post_schema_candidate(
    candidate: SchemaValidatedCandidate,
    *,
    schema_registry: CanonicalOutputSchemaRegistry,
) -> None:
    """Run only the frozen text cross-field check on a typed candidate."""
    payload = _detached_payload_for_schema(
        candidate,
        expected_schema_id="text_output_schema_v1",
        schema_registry=schema_registry,
    )
    validate_text_cross_fields(payload)


def validate_visual_post_schema_candidate(
    candidate: SchemaValidatedCandidate,
    *,
    schema_registry: CanonicalOutputSchemaRegistry,
    supplied_image_count: int,
) -> None:
    """Run only the frozen visual photo-reference check on a typed candidate."""
    payload = _detached_payload_for_schema(
        candidate,
        expected_schema_id="visual_output_schema_v1",
        schema_registry=schema_registry,
    )
    validate_visual_photo_references(payload, supplied_image_count)
