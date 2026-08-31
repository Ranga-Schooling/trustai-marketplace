"""Strict local identity verification for frozen evaluation contracts."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any


_LOWER_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class ContractIdentityError(ValueError):
    """A frozen contract cannot be parsed or its identity does not match."""


@dataclass(frozen=True)
class ContractSetIdentity:
    child_hashes: tuple[tuple[str, str], ...]
    set_hash: str


@dataclass(frozen=True)
class NormalizationSpecIdentity:
    child_hashes: tuple[tuple[str, str], ...]
    semantic_hash: str


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractIdentityError("strict_contract_json:duplicate_key")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise ContractIdentityError(f"strict_contract_json:nonfinite:{value}")


def _contains_surrogate(value: Any) -> bool:
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, str):
            if any("\ud800" <= character <= "\udfff" for character in current):
                return True
        elif isinstance(current, dict):
            pending.extend(current.keys())
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    return False


def load_strict_contract_json(path: str | Path) -> dict[str, Any]:
    """Read one contract with strict UTF-8, duplicate, and scalar checks."""
    try:
        raw = Path(path).read_bytes()
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite,
        )
        if not isinstance(value, dict) or _contains_surrogate(value):
            raise ContractIdentityError("strict_contract_json:root_or_unicode")
        return value
    except ContractIdentityError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ContractIdentityError("strict_contract_json:invalid") from exc


def _parse_spec_integer(lexeme: str) -> int:
    if lexeme == "-0":
        raise ContractIdentityError("strict_contract_json:negative_zero")
    value = int(lexeme)
    if value < -9007199254740991 or value > 9007199254740991:
        raise ContractIdentityError("strict_contract_json:integer_domain")
    return value


def _reject_spec_noninteger(lexeme: str) -> None:
    raise ContractIdentityError(f"strict_contract_json:noninteger:{lexeme}")


def load_strict_normalization_spec(path: str | Path) -> dict[str, Any]:
    """Load the parser spec under canonical_parser_policy_json_v1 preconditions."""
    try:
        raw = Path(path).read_bytes()
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_int=_parse_spec_integer,
            parse_float=_reject_spec_noninteger,
            parse_constant=_reject_nonfinite,
        )
        if not isinstance(value, dict) or _contains_surrogate(value):
            raise ContractIdentityError("strict_contract_json:root_or_unicode")
        return value
    except ContractIdentityError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ContractIdentityError("strict_contract_json:invalid") from exc


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ContractIdentityError("canonical_contract_json:invalid") from exc


def _sha256_canonical(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _validate_stored_hash(label: str, value: Any) -> str:
    if not isinstance(value, str) or _LOWER_SHA256.fullmatch(value) is None:
        raise ContractIdentityError(f"{label}:invalid_hash")
    return value


def _verify_children(
    *,
    records: Any,
    declared_order: Any,
    id_field: str,
    hash_field: str,
) -> tuple[tuple[str, str], ...]:
    if not isinstance(records, list) or not isinstance(declared_order, list):
        raise ContractIdentityError("ordered_inventory:invalid")
    identifiers = tuple(record.get(id_field) for record in records)
    if identifiers != tuple(declared_order) or len(set(identifiers)) != len(
        identifiers
    ):
        raise ContractIdentityError("ordered_inventory:mismatch")

    verified: list[tuple[str, str]] = []
    for record in records:
        identifier = record[id_field]
        stored_hash = _validate_stored_hash(hash_field, record.get(hash_field))
        content = {key: value for key, value in record.items() if key != hash_field}
        computed_hash = _sha256_canonical(content)
        if computed_hash != stored_hash:
            raise ContractIdentityError(f"child_hash_mismatch:{identifier}")
        verified.append((identifier, computed_hash))
    return tuple(verified)


def _require_fields(artifact: dict[str, Any], fields: tuple[str, ...]) -> None:
    missing = tuple(field for field in fields if field not in artifact)
    if missing:
        raise ContractIdentityError("set_identity_missing_field")


def verify_output_schema_artifact(
    artifact: dict[str, Any],
) -> ContractSetIdentity:
    """Recompute every schema record and the exact frozen schema-set hash."""
    if not isinstance(artifact, dict):
        raise ContractIdentityError("schema_artifact_type")
    set_fields = (
        "schema_version",
        "output_schema_set_version",
        "json_schema_dialect",
        "provider_neutral",
        "pilot_and_scored_shared",
        "semantic_sources",
        "schema_order",
        "global_policies",
        "validator_declarations",
        "schemas",
        "schema_canonicalization",
        "schema_set_sha256",
    )
    _require_fields(artifact, set_fields)
    children = _verify_children(
        records=artifact["schemas"],
        declared_order=artifact["schema_order"],
        id_field="schema_id",
        hash_field="schema_sha256",
    )
    set_content = {
        "schema_version": artifact["schema_version"],
        "output_schema_set_version": artifact["output_schema_set_version"],
        "json_schema_dialect": artifact["json_schema_dialect"],
        "provider_neutral": artifact["provider_neutral"],
        "pilot_and_scored_shared": artifact["pilot_and_scored_shared"],
        "semantic_sources": artifact["semantic_sources"],
        "schema_canonicalization_id": artifact["schema_canonicalization"][
            "schema_canonicalization_id"
        ],
        "schema_order": artifact["schema_order"],
        "global_policies": artifact["global_policies"],
        "validator_declarations": artifact["validator_declarations"],
        "schemas": [
            {"schema_id": identifier, "schema_sha256": child_hash}
            for identifier, child_hash in children
        ],
    }
    computed_set_hash = _sha256_canonical(set_content)
    stored_set_hash = _validate_stored_hash(
        "schema_set_sha256",
        artifact["schema_set_sha256"],
    )
    if computed_set_hash != stored_set_hash:
        raise ContractIdentityError("set_hash_mismatch:schema")
    return ContractSetIdentity(children, computed_set_hash)


def verify_prompt_template_artifact(
    artifact: dict[str, Any],
) -> ContractSetIdentity:
    """Recompute every template record and the exact frozen template-set hash."""
    if not isinstance(artifact, dict):
        raise ContractIdentityError("prompt_artifact_type")
    direct_fields = (
        "prompt_template_set_version",
        "semantic_source",
        "provider_neutral",
        "pilot_and_scored_substantive_templates_shared",
        "source_commits",
        "template_order",
        "injection_authority_model",
        "output_contracts",
        "provider_specific_terminology_forbidden_in_canonical_content",
        "leakage_boundary",
        "untrusted_value_rendering_policy",
        "rendered_run_record_requirements",
        "pilot_scored_relationship",
        "templates",
        "canonicalization",
        "prompt_template_set_hash",
    )
    _require_fields(artifact, direct_fields)
    children = _verify_children(
        records=artifact["templates"],
        declared_order=artifact["template_order"],
        id_field="template_id",
        hash_field="canonical_sha256",
    )
    set_content = {
        "canonicalization_version": artifact["canonicalization"]["version"],
        **{
            field: artifact[field]
            for field in direct_fields[:13]
            if field != "templates"
        },
        "templates": [
            {"template_id": identifier, "canonical_sha256": child_hash}
            for identifier, child_hash in children
        ],
    }
    computed_set_hash = _sha256_canonical(set_content)
    stored_set_hash = _validate_stored_hash(
        "prompt_template_set_hash",
        artifact["prompt_template_set_hash"],
    )
    if computed_set_hash != stored_set_hash:
        raise ContractIdentityError("set_hash_mismatch:prompt")
    return ContractSetIdentity(children, computed_set_hash)


def _pointer_segments(pointer: str) -> tuple[str, ...]:
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ContractIdentityError("json_pointer:invalid")
    segments = []
    for encoded in pointer[1:].split("/"):
        index = 0
        decoded: list[str] = []
        while index < len(encoded):
            character = encoded[index]
            if character != "~":
                decoded.append(character)
                index += 1
                continue
            if index + 1 >= len(encoded) or encoded[index + 1] not in {"0", "1"}:
                raise ContractIdentityError("json_pointer:invalid_escape")
            decoded.append("~" if encoded[index + 1] == "0" else "/")
            index += 2
        segments.append("".join(decoded))
    return tuple(segments)


def _resolve_pointer(document: Any, pointer: str) -> Any:
    current = document
    for segment in _pointer_segments(pointer):
        if isinstance(current, dict):
            if segment not in current:
                raise ContractIdentityError("json_pointer:missing")
            current = current[segment]
        elif isinstance(current, list):
            if not segment.isdigit() or (len(segment) > 1 and segment.startswith("0")):
                raise ContractIdentityError("json_pointer:invalid_index")
            index = int(segment)
            if index >= len(current):
                raise ContractIdentityError("json_pointer:missing")
            current = current[index]
        else:
            raise ContractIdentityError("json_pointer:non_container")
    return current


def _delete_pointer(document: Any, pointer: str) -> None:
    segments = _pointer_segments(pointer)
    if not segments:
        raise ContractIdentityError("json_pointer:root_deletion_forbidden")
    parent = document
    for segment in segments[:-1]:
        if isinstance(parent, dict) and segment in parent:
            parent = parent[segment]
        elif isinstance(parent, list) and segment.isdigit():
            index = int(segment)
            if index >= len(parent):
                raise ContractIdentityError("json_pointer:missing")
            parent = parent[index]
        else:
            raise ContractIdentityError("json_pointer:missing")
    final = segments[-1]
    if isinstance(parent, dict) and final in parent:
        del parent[final]
    elif isinstance(parent, list) and final.isdigit() and int(final) < len(parent):
        del parent[int(final)]
    else:
        raise ContractIdentityError("json_pointer:missing")


def _filtered_copy(document: Any, pointers: Any) -> Any:
    if not isinstance(pointers, list) or len(pointers) != len(set(pointers)):
        raise ContractIdentityError("exclusion_pointer_inventory")
    result = copy.deepcopy(document)
    for pointer in pointers:
        _resolve_pointer(result, pointer)
        _delete_pointer(result, pointer)
    return result


def _declared_policy_identity(subtree: dict[str, Any]) -> set[str]:
    return {
        value
        for key, value in subtree.items()
        if isinstance(value, str)
        and (key == "policy_id" or key.endswith("_id") or key == "interface_id")
    }


def verify_normalization_parser_artifact(
    artifact: dict[str, Any],
) -> NormalizationSpecIdentity:
    """Recompute the central parser identity and all 49 child identities."""
    try:
        identity = artifact["specification_identity"]
        registry = identity["embedded_policy_registry"]
        cache = identity["derived_hash_cache"]
        cached_children = cache["registered_policy_semantic_hashes"]
        child_exclusions = identity["child_policy_exact_exclusions"]
        spec_exclusions = identity["specification_semantic_excluded_json_pointers"]
    except (KeyError, TypeError) as exc:
        raise ContractIdentityError("normalization_identity_shape") from exc
    if not isinstance(registry, dict) or len(registry) != 49:
        raise ContractIdentityError("registry_inventory")
    if set(cached_children) != set(registry):
        raise ContractIdentityError("child_cache_inventory")

    pointers: set[str] = set()
    version_pairs: set[tuple[str, str]] = set()
    computed_children: list[tuple[str, str]] = []
    for registry_key, record in registry.items():
        if record.get("policy_id") != registry_key:
            raise ContractIdentityError("registry_policy_id")
        version = record.get("policy_version")
        pointer = record.get("json_pointer")
        pair = (registry_key, version)
        if pair in version_pairs or pointer in pointers:
            raise ContractIdentityError("registry_identity_duplicate")
        version_pairs.add(pair)
        pointers.add(pointer)

        subtree = _resolve_pointer(artifact, pointer)
        if (
            not isinstance(subtree, dict)
            or registry_key not in _declared_policy_identity(subtree)
        ):
            raise ContractIdentityError("registry_subtree_identity")
        declared_version = subtree.get("version") or subtree.get("policy_version")
        if declared_version is not None and declared_version != version:
            raise ContractIdentityError("registry_subtree_version")
        exclusions = child_exclusions.get(registry_key, [])
        child_content = _filtered_copy(subtree, exclusions)
        envelope = {
            "identity_domain": "trustai.embedded_policy.v1",
            "policy_id": registry_key,
            "policy_version": version,
            "content": child_content,
        }
        computed = _sha256_canonical(envelope)
        expected = _validate_stored_hash(
            "expected_semantic_hash",
            record.get("expected_semantic_hash"),
        )
        cached = _validate_stored_hash(
            "registered_policy_semantic_hash",
            cached_children.get(registry_key),
        )
        if computed != expected or computed != cached:
            raise ContractIdentityError(f"child_hash_mismatch:{registry_key}")
        computed_children.append((registry_key, computed))

    filtered_spec = _filtered_copy(artifact, spec_exclusions)
    spec_envelope = {
        "identity_domain": "trustai.normalization_spec.v1",
        "normalization_spec_id": identity["normalization_spec_id"],
        "normalization_spec_version": identity["normalization_spec_version"],
        "content": filtered_spec,
    }
    computed_spec_hash = _sha256_canonical(spec_envelope)
    cached_spec_hash = _validate_stored_hash(
        "normalization_spec_semantic_hash",
        cache["normalization_spec_semantic_hash"],
    )
    if computed_spec_hash != cached_spec_hash:
        raise ContractIdentityError("spec_hash_mismatch")
    return NormalizationSpecIdentity(tuple(computed_children), computed_spec_hash)
