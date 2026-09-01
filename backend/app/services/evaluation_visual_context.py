"""Frozen, provider-neutral pilot Visual Inspection context projection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from typing import Any


_EXPECTED_HASH = "7e6c51a9484f7e9de6910caa829728298b5e4d787af52106e9e2797ddbcae961"
_PROMPT_SET_HASH = "9d6c5e43acb971b3ffb2a47b69f0def142d21c971717541e007f711404603df2"
_TEMPLATE_HASH = "4f04c3c60db5803e22e6d197e22b28ea1a769dea61038a714b96657414ddc156"
_CONTEXT_KEYS = ("title", "description")
_EXPECTED_CONTEXT_HASHES = {
    "PV1": "1e5c19392ec97367675dddf5be2b9b8313c33f265900d31fc56eef65ffe55cba",
    "PV2": "322ffd7b86c78939530229042553048f5c30a0a3f81da968d071d960e310d5e3",
}


class VisualContextContractError(ValueError):
    """The pilot visual-context shape or source binding fails closed."""

    category = "topology_preflight_failure"
    provider_attempt_created = False
    provider_call_incremented = False


@dataclass(frozen=True, slots=True)
class FrozenVisualContextContract:
    artifact_id: str
    artifact_version: str
    semantic_hash: str
    context_keys: tuple[str, ...]
    fixture_ids: tuple[str, ...]
    fixture_contexts: tuple[tuple[str, Mapping[str, str]], ...]
    rendering_policy_id: str
    rendering_policy_version: str
    provider_calls_allowed: bool = False
    pilot_calls_allowed: bool = False
    provider_calls_completed: int = 0
    independently_authorizes_execution: bool = False


@dataclass(frozen=True, slots=True)
class RenderedPilotVisualContext:
    fixture_id: str
    provider_visible_context: Mapping[str, str]
    canonical_json: str
    canonical_json_sha256: str
    authority_class: str = "untrusted_context"
    provider_attempt_created: bool = False
    provider_call_incremented: bool = False


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise VisualContextContractError("canonical_json") from exc


def _artifact_hash(raw: Mapping[str, Any]) -> str:
    detached = json.loads(_canonical(raw))
    detached["specification_identity"]["semantic_hash"] = None
    return hashlib.sha256(_canonical(detached)).hexdigest()


def _visual_fixture_contexts(pilot: Mapping[str, Any]) -> dict[str, Mapping[str, str]]:
    fixtures = pilot.get("pilot_fixtures")
    if type(fixtures) is not list:
        raise VisualContextContractError("pilot_fixtures")
    result: dict[str, Mapping[str, str]] = {}
    for fixture in fixtures:
        if type(fixture) is not dict or fixture.get("id") not in _EXPECTED_CONTEXT_HASHES:
            continue
        context = fixture.get("sanitized_listing_context")
        if (
            type(context) is not dict
            or tuple(context) != _CONTEXT_KEYS
            or any(type(context[key]) is not str or not context[key] for key in _CONTEXT_KEYS)
        ):
            raise VisualContextContractError("fixture_context_shape")
        result[fixture["id"]] = context
    if tuple(result) != ("PV1", "PV2"):
        raise VisualContextContractError("fixture_inventory")
    return result


def _visual_prompt(prompt: Mapping[str, Any]) -> Mapping[str, Any]:
    if (
        prompt.get("prompt_template_set_version") != "v1"
        or prompt.get("prompt_template_set_hash") != _PROMPT_SET_HASH
    ):
        raise VisualContextContractError("prompt_set")
    templates = prompt.get("templates")
    if type(templates) is not list:
        raise VisualContextContractError("prompt_templates")
    matches = [item for item in templates if item.get("template_id") == "visual_context_v1"]
    if len(matches) != 1:
        raise VisualContextContractError("visual_prompt")
    visual = matches[0]
    if (
        visual.get("canonical_sha256") != _TEMPLATE_HASH
        or visual.get("placeholder_allowlist") != ["sanitized_listing_context"]
        or visual.get("dynamic_data_rendering", {}).get("rendering_policy_ref")
        != "canonical_untrusted_json_v1@v1"
        or visual.get("provider_calls_blocked_while_context_shape_pending") is not True
    ):
        raise VisualContextContractError("visual_prompt_binding")
    return visual


def bind_visual_context_contract(
    raw: Mapping[str, Any],
    pilot: Mapping[str, Any],
    prompt: Mapping[str, Any],
) -> FrozenVisualContextContract:
    """Bind the external V1 context resolution without mutating frozen inputs."""
    if (
        type(raw) is not dict
        or raw.get("artifact_id") != "pilot_visual_context_v1"
        or raw.get("artifact_version") != "v1"
        or raw.get("status") != "frozen_pre_execution_contract"
        or raw.get("specification_identity", {}).get("semantic_hash") != _EXPECTED_HASH
        or _artifact_hash(raw) != _EXPECTED_HASH
    ):
        raise VisualContextContractError("artifact")
    _visual_prompt(prompt)
    source_contexts = _visual_fixture_contexts(pilot)
    shape = raw.get("provider_visible_shape")
    if (
        type(shape) is not dict
        or shape.get("keys_in_allowlist_order") != list(_CONTEXT_KEYS)
        or shape.get("required_keys") != list(_CONTEXT_KEYS)
        or shape.get("additional_properties") is not False
        or shape.get("value_types")
        != {"title": "nonempty_string", "description": "nonempty_string"}
        or shape.get("whole_fixture_serialization_forbidden") is not True
        or shape.get("fixture_id_provider_visible") is not False
        or shape.get("truth_or_grading_metadata_provider_visible") is not False
        or shape.get("asset_identity_or_hash_provider_visible") is not False
    ):
        raise VisualContextContractError("provider_visible_shape")
    rendering = raw.get("rendering")
    if (
        type(rendering) is not dict
        or rendering.get("rendering_policy_id") != "canonical_untrusted_json_v1"
        or rendering.get("rendering_policy_version") != "v1"
        or rendering.get("authority_class") != "untrusted_context"
        or rendering.get("image_bytes_in_rendered_context") is not False
    ):
        raise VisualContextContractError("rendering")
    records = raw.get("fixture_contexts")
    if type(records) is not list or [item.get("fixture_id") for item in records] != [
        "PV1", "PV2"
    ]:
        raise VisualContextContractError("context_inventory")
    bound: list[tuple[str, Mapping[str, str]]] = []
    for record in records:
        fixture_id = record["fixture_id"]
        context = record.get("provider_visible_context")
        canonical = _canonical(context)
        digest = hashlib.sha256(canonical).hexdigest()
        if (
            context != source_contexts[fixture_id]
            or digest != _EXPECTED_CONTEXT_HASHES[fixture_id]
            or record.get("canonical_json_sha256") != digest
        ):
            raise VisualContextContractError("context_binding")
        bound.append((fixture_id, dict(context)))
    adapter = raw.get("adapter_binding")
    if (
        type(adapter) is not dict
        or adapter.get("workload_stage") != "visual_inspection"
        or adapter.get("topology_id") != "single_call_visual"
        or adapter.get("text_segment_source")
        != "untrusted_context components in exact manifest order"
        or adapter.get("text_precedes_image") is not True
        or adapter.get("provider_specific_content_added") is not False
    ):
        raise VisualContextContractError("adapter_binding")
    boundary = raw.get("execution_boundary")
    if (
        type(boundary) is not dict
        or boundary.get("execution_state") != "blocked_pre_execution"
        or boundary.get("provider_calls_allowed") is not False
        or boundary.get("pilot_calls_allowed") is not False
        or boundary.get("scored_calls_allowed") is not False
        or boundary.get("provider_calls_completed") != 0
        or boundary.get("pilot_calls_completed") != 0
        or boundary.get("scored_calls_completed") != 0
        or boundary.get("winner_selected") is not False
        or boundary.get("this_artifact_independently_authorizes_execution") is not False
    ):
        raise VisualContextContractError("execution_boundary")
    return FrozenVisualContextContract(
        artifact_id=raw["artifact_id"],
        artifact_version=raw["artifact_version"],
        semantic_hash=_EXPECTED_HASH,
        context_keys=_CONTEXT_KEYS,
        fixture_ids=("PV1", "PV2"),
        fixture_contexts=tuple(bound),
        rendering_policy_id=rendering["rendering_policy_id"],
        rendering_policy_version=rendering["rendering_policy_version"],
    )


def render_pilot_visual_context(
    contract: FrozenVisualContextContract,
    *,
    fixture_id: str,
) -> RenderedPilotVisualContext:
    matches = [context for identifier, context in contract.fixture_contexts if identifier == fixture_id]
    if len(matches) != 1:
        raise VisualContextContractError("fixture_selection")
    context = dict(matches[0])
    canonical = _canonical(context)
    return RenderedPilotVisualContext(
        fixture_id=fixture_id,
        provider_visible_context=context,
        canonical_json=canonical.decode("utf-8"),
        canonical_json_sha256=hashlib.sha256(canonical).hexdigest(),
    )
