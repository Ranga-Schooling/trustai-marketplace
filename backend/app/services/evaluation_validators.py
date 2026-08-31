"""Pure deterministic validators for schema-valid evaluation candidates."""

from __future__ import annotations

from typing import Any


class DeterministicValidationError(ValueError):
    """One frozen post-schema validator rejected a canonical candidate."""

    def __init__(
        self,
        *,
        validator_id: str,
        terminal_outcome: str,
        reason: str,
    ) -> None:
        super().__init__(f"{validator_id}:{reason}")
        self.validator_id = validator_id
        self.terminal_outcome = terminal_outcome
        self.reason = reason


def _reject(validator_id: str, terminal_outcome: str, reason: str) -> None:
    raise DeterministicValidationError(
        validator_id=validator_id,
        terminal_outcome=terminal_outcome,
        reason=reason,
    )


def validate_text_cross_fields(candidate: dict[str, Any]) -> None:
    """Enforce the frozen indicator/risk/recommendation relationship.

    ``candidate`` must already have passed ``text_output_schema_v1``.  The
    function only accepts or rejects; it never repairs any model-owned field.
    """
    severities = tuple(
        indicator["severity"] for indicator in candidate["risk_indicators"]
    )
    if "high" in severities:
        expected_risk = "high"
    elif "medium" in severities:
        expected_risk = "medium"
    else:
        expected_risk = "low"

    if candidate["risk_level"] != expected_risk:
        _reject(
            "text_cross_field_validator_v1",
            "failed_cross_field_validation",
            "risk_level_indicator_mismatch",
        )

    expected_recommendation = {
        "low": "buy",
        "medium": "caution",
        "high": "avoid",
    }[candidate["risk_level"]]
    if candidate["recommendation"] != expected_recommendation:
        _reject(
            "text_cross_field_validator_v1",
            "failed_cross_field_validation",
            "risk_recommendation_mismatch",
        )


def validate_visual_photo_references(
    candidate: dict[str, Any],
    supplied_image_count: int,
) -> None:
    """Reject any schema-valid photo reference absent from the actual input."""
    if (
        type(supplied_image_count) is not int
        or supplied_image_count < 1
        or supplied_image_count > 3
    ):
        raise ValueError("supplied_image_count must be an integer from 1 to 3")

    for finding in candidate["findings"]:
        if any(
            photo_number > supplied_image_count
            for photo_number in finding["photo_numbers"]
        ):
            _reject(
                "visual_photo_reference_validator_v1",
                "failed_cross_field_validation",
                "photo_number_exceeds_supplied_count",
            )


_SOURCE_PROJECTION_FIELDS = (
    "source_id",
    "name",
    "url",
    "source_type",
    "retrieved_at",
)


def _reject_search(reason: str) -> None:
    _reject(
        "search_cross_reference_validator_v1",
        "failed_trace_validation",
        reason,
    )


def _unique_ids(records: list[dict[str, Any]], field: str, namespace: str) -> None:
    values = tuple(record[field] for record in records)
    if len(values) != len(set(values)):
        _reject_search(f"duplicate_{namespace}_id")


def _numeric_value(value: Any) -> Any:
    return getattr(value, "exact_decimal", value)


def validate_search_cross_references(
    candidate: dict[str, Any],
    validated_retrieval_bundle: dict[str, Any],
) -> None:
    """Validate frozen search-result identity, projection, and references.

    Both inputs must already be canonical-schema-valid and the retrieval bundle
    must already be fully validated.  This function performs no source
    classification, semantic entailment, repair, or ID generation.
    """
    bundle_sources = validated_retrieval_bundle["sources"]
    _unique_ids(bundle_sources, "source_id", "retrieval_source")
    canonical_sources = {source["source_id"]: source for source in bundle_sources}

    final_sources = candidate["sources"]
    _unique_ids(final_sources, "source_id", "source")
    selected_sources = {source["source_id"]: source for source in final_sources}
    for source_id, source in selected_sources.items():
        canonical = canonical_sources.get(source_id)
        if canonical is None:
            _reject_search("unknown_source_reference")
        expected_projection = {
            field: canonical[field] for field in _SOURCE_PROJECTION_FIELDS
        }
        if source != expected_projection:
            _reject_search("source_projection_mismatch")

    _unique_ids(candidate["claims"], "claim_id", "claim")
    _unique_ids(candidate["price_evidence"], "price_evidence_id", "price_evidence")
    _unique_ids(candidate["uncertainties"], "uncertainty_id", "uncertainty")
    _unique_ids(candidate["conflicts"], "conflict_id", "conflict")

    referenced_source_ids: list[str] = list(
        candidate["identity_resolution"]["source_ids"]
    )
    for claim in candidate["claims"]:
        referenced_source_ids.extend(claim["source_ids"])
    for price in candidate["price_evidence"]:
        referenced_source_ids.append(price["source_id"])
        value = price["price_value"]
        if value["kind"] == "range" and _numeric_value(
            value["minimum"]
        ) > _numeric_value(value["maximum"]):
            _reject_search("inverted_price_range")
    for uncertainty in candidate["uncertainties"]:
        referenced_source_ids.extend(uncertainty["source_ids"])
    for conflict in candidate["conflicts"]:
        referenced_source_ids.extend(conflict["source_ids"])

    if any(
        source_id not in canonical_sources or source_id not in selected_sources
        for source_id in referenced_source_ids
    ):
        _reject_search("unknown_source_reference")

    identity = candidate["identity_resolution"]
    identity_status = identity["status"]
    identity_source_ids = set(identity["source_ids"])
    has_resolved_identity = "resolved_product_identity" in identity
    has_resolved_variant = "resolved_variant_or_sku" in identity
    if identity_status == "resolved":
        if not has_resolved_identity or not identity_source_ids:
            _reject_search("resolved_identity_incomplete")
    elif has_resolved_identity or has_resolved_variant:
        _reject_search("resolved_identity_field_forbidden")

    if identity_status == "conflicting":
        identity_conflicts = tuple(
            conflict
            for conflict in candidate["conflicts"]
            if conflict["conflict_type"] in {"identity", "variant"}
            and set(conflict["source_ids"]).issubset(identity_source_ids)
        )
        if len(identity_source_ids) < 2 or not identity_conflicts:
            _reject_search("identity_conflict_missing")

    current_status = identity["current_status"]
    if current_status in {"current", "discontinued"} and not identity_source_ids:
        _reject_search("current_status_source_missing")
    if current_status == "conflicting":
        status_conflicts = tuple(
            conflict
            for conflict in candidate["conflicts"]
            if conflict["conflict_type"] == "status"
            and set(conflict["source_ids"]).issubset(identity_source_ids)
        )
        if len(identity_source_ids) < 2 or not status_conflicts:
            _reject_search("status_conflict_missing")

    comparison_status = candidate["comparison_status"]
    has_material_result = bool(candidate["claims"] or candidate["price_evidence"])
    if comparison_status == "established":
        if (
            identity_status != "resolved"
            or not selected_sources
            or not has_material_result
        ):
            _reject_search("established_comparison_incomplete")
    elif comparison_status == "partially_established":
        if not has_material_result or not (
            candidate["uncertainties"] or candidate["conflicts"]
        ):
            _reject_search("partial_comparison_incoherent")
    elif not any(
        uncertainty["uncertainty_type"]
        in {"insufficient_evidence", "unresolved_identity"}
        for uncertainty in candidate["uncertainties"]
    ):
        _reject_search("not_established_uncertainty_missing")


def validate_retrieval_status_coherence(
    retrieval_status: str,
    material_objective_support: tuple[str, ...],
    source_count: int,
) -> None:
    """Validate, but never select or replace, provider retrieval status."""
    allowed_statuses = {"completed", "partial", "no_reliable_evidence"}
    allowed_support = {"sufficient", "insufficient", "conflicting"}
    if (
        retrieval_status not in allowed_statuses
        or not isinstance(material_objective_support, tuple)
        or not material_objective_support
        or any(value not in allowed_support for value in material_objective_support)
        or type(source_count) is not int
        or source_count < 0
    ):
        raise ValueError("invalid retrieval_status_coherence input")

    sufficient_count = material_objective_support.count("sufficient")
    if sufficient_count == len(material_objective_support):
        coherent_status = "completed"
    elif sufficient_count:
        coherent_status = "partial"
    else:
        coherent_status = "no_reliable_evidence"

    minimum_sources = 0 if coherent_status == "no_reliable_evidence" else 1
    if retrieval_status != coherent_status or source_count < minimum_sources:
        _reject(
            "retrieval_status_coherence_validator_v1",
            "failed_retrieval_coherence",
            "retrieval_status_mismatch",
        )
