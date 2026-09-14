"""Independent cross-language conformance for frozen normalization identity."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, Callable

import pytest

from app.services.evaluation_contract_identity import (
    ContractIdentityError,
    load_strict_contract_json,
    load_strict_normalization_spec,
    verify_output_schema_artifact,
    verify_normalization_parser_artifact,
    verify_prompt_template_artifact,
)


pytestmark = pytest.mark.contract


ROOT = Path(__file__).parents[2]
ARTIFACT_DIRECTORY = ROOT / "docs" / "testing" / "ai-evaluation"
PARSER_PATH = ROOT / "docs" / "testing" / "ai-evaluation" / (
    "normalization-parser.v1.json"
)
PROMPT_PATH = ARTIFACT_DIRECTORY / "prompt-templates.v1.json"
SCHEMA_PATH = ARTIFACT_DIRECTORY / "output-schemas.v1.json"
EXPERIMENT_PATH = ARTIFACT_DIRECTORY / "experiment.v1.json"
REFERENCE_PATH = Path(__file__).parent / "reference" / (
    "normalization_spec_identity_reference.mjs"
)
PROMPT_SET_HASH = (
    "9d6c5e43acb971b3ffb2a47b69f0def142d21c971717541e007f711404603df2"
)
SCHEMA_SET_HASH = (
    "125809d08e911d51b4619002f02a969b03b8da5866bfab1b8346758c0bb9a6f4"
)
SPEC_FILE_HASH = (
    "fbf7438d1e283ee29ce5559762e2ada79079da0684adf26dae1216422a6338e9"
)
SPEC_HASH = "023ad80eeb6e08e9279c22b7955ebe5d04ec9ab3cd88626ceaccc4962c41b343"
REFERENCE_SHA256 = (
    "5c0d3d25aa4e3fa8d99aef7654fe8a6285a9049f8b84f2a8961cc1d0020febf5"
)


def _run_reference(
    path: Path = PARSER_PATH,
    *,
    authorized_spec_hash: str = SPEC_HASH,
    prompt_hash: str = PROMPT_SET_HASH,
    schema_hash: str = SCHEMA_SET_HASH,
    include_canonical: bool = False,
    analyze: bool = False,
    parse_only: bool = False,
) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    assert node is not None, "Node is required for the independent reference"
    command = [
        node,
        str(REFERENCE_PATH),
        str(path),
        authorized_spec_hash,
        prompt_hash,
        schema_hash,
    ]
    if include_canonical:
        command.append("--include-canonical")
    if analyze:
        command.append("--analyze")
    if parse_only:
        command.append("--parse-only")
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _result(completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return json.loads(completed.stdout)


def _segments(pointer: str) -> tuple[str, ...]:
    result = []
    for encoded in pointer[1:].split("/"):
        result.append(encoded.replace("~1", "/").replace("~0", "~"))
    return tuple(result)


def _resolve(document: Any, pointer: str) -> Any:
    current = document
    for segment in _segments(pointer):
        current = current[int(segment)] if isinstance(current, list) else current[segment]
    return current


def _delete(document: Any, pointer: str) -> None:
    segments = _segments(pointer)
    parent = document
    for segment in segments[:-1]:
        parent = parent[int(segment)] if isinstance(parent, list) else parent[segment]
    final = segments[-1]
    if isinstance(parent, list):
        del parent[int(final)]
    else:
        del parent[final]


def _filtered(document: Any, pointers: list[str]) -> Any:
    result = copy.deepcopy(document)
    for pointer in pointers:
        _resolve(document, pointer)
    for pointer in pointers:
        _delete(result, pointer)
    return result


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _expected_canonical_bytes(
    artifact: dict[str, Any],
) -> tuple[bytes, dict[str, bytes]]:
    identity = artifact["specification_identity"]
    children = {}
    child_exclusions = identity["child_policy_exact_exclusions"]
    for policy_id, record in identity["embedded_policy_registry"].items():
        subtree = _resolve(artifact, record["json_pointer"])
        envelope = {
            "identity_domain": "trustai.embedded_policy.v1",
            "policy_id": record["policy_id"],
            "policy_version": record["policy_version"],
            "content": _filtered(subtree, child_exclusions.get(policy_id, [])),
        }
        children[policy_id] = _canonical_bytes(envelope)
    spec_envelope = {
        "identity_domain": "trustai.normalization_spec.v1",
        "normalization_spec_id": identity["normalization_spec_id"],
        "normalization_spec_version": identity["normalization_spec_version"],
        "content": _filtered(
            artifact,
            identity["specification_semantic_excluded_json_pointers"],
        ),
    }
    return _canonical_bytes(spec_envelope), children


def _identity_snapshot(
    artifact: dict[str, Any],
) -> tuple[dict[str, str], str]:
    spec_bytes, child_bytes = _expected_canonical_bytes(artifact)
    return (
        {
            policy_id: hashlib.sha256(content).hexdigest()
            for policy_id, content in child_bytes.items()
        },
        hashlib.sha256(spec_bytes).hexdigest(),
    )


def _write_artifact(path: Path, artifact: dict[str, Any], **kwargs: Any) -> None:
    defaults = {"ensure_ascii": False, "indent": 2}
    defaults.update(kwargs)
    path.write_text(json.dumps(artifact, **defaults) + "\n", encoding="utf-8")


def test_independent_reference_recomputes_all_frozen_identities():
    artifact = load_strict_normalization_spec(PARSER_PATH)
    python_identity = verify_normalization_parser_artifact(artifact)
    prompt_identity = verify_prompt_template_artifact(
        load_strict_contract_json(PROMPT_PATH)
    )
    schema_identity = verify_output_schema_artifact(
        load_strict_contract_json(SCHEMA_PATH)
    )

    completed = _run_reference(include_canonical=True)

    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    result = _result(completed)
    assert result["valid"] is True
    assert result["implementation_id"] == (
        "normalization_spec_identity_javascript_reference_v1"
    )
    assert result["normalization_spec_file_sha256"] == SPEC_FILE_HASH
    assert result["normalization_spec_semantic_hash"] == SPEC_HASH
    assert result["normalization_spec_semantic_hash"] == python_identity.semantic_hash
    assert result["child_hashes"] == dict(python_identity.child_hashes)
    assert len(result["child_hashes"]) == 49
    assert result["canonical_bootstrap_self_test"] is True
    assert result["pointer_bootstrap_self_test"] is True
    assert result["provider_calls_required"] is False
    assert prompt_identity.set_hash == PROMPT_SET_HASH
    assert schema_identity.set_hash == SCHEMA_SET_HASH

    spec_bytes, child_bytes = _expected_canonical_bytes(artifact)
    assert base64.b64decode(result["normalization_spec_canonical_base64"]) == spec_bytes
    assert {
        policy_id: base64.b64decode(encoded)
        for policy_id, encoded in result["child_canonical_base64"].items()
    } == child_bytes


def test_reference_source_is_independent_provider_free_and_non_authorizing():
    assert hashlib.sha256(REFERENCE_PATH.read_bytes()).hexdigest() == REFERENCE_SHA256
    source = REFERENCE_PATH.read_text(encoding="utf-8")
    experiment = load_strict_contract_json(EXPERIMENT_PATH)
    execution_gate = experiment["execution_gate"]

    assert [
        line for line in source.splitlines() if line.startswith("import ")
    ] == [
        'import { createHash } from "node:crypto";',
        'import { readFileSync } from "node:fs";',
    ]
    assert "from app" not in source
    assert "evaluation_contract_identity" not in source
    assert "JSON.parse(" not in source
    assert "fetch(" not in source
    assert "https://" not in source
    assert "process.env" not in source
    assert "OPENAI" not in source
    assert "GROQ" not in source
    assert "GEMINI" not in source
    assert execution_gate["overall_status"] == "blocked_pre_execution"
    assert execution_gate["provider_calls_allowed"] is False
    assert execution_gate["pilot_calls_allowed"] is False
    assert execution_gate["scored_calls_allowed"] is False
    assert experiment["provider_calls_completed"] == 0
    assert experiment["scored_provider_calls_completed"] == 0
    assert experiment["winner_selected"] is False


@pytest.mark.parametrize(
    ("case_id", "raw", "error_prefix"),
    [
        ("duplicate_decoded_key", b'{"x":1,"\\u0078":2}', "strict_json:duplicate_key"),
        (
            "duplicate_supplementary_key",
            '{"😀":1,"\\ud83d\\ude00":2}'.encode(),
            "strict_json:duplicate_key",
        ),
        ("nested_duplicate_key", b'{"a":{"x":1,"x":2}}', "strict_json:duplicate_key"),
        ("utf8", b'{"x":"\xff"}', "strict_json:utf8"),
        ("bom", b"\xef\xbb\xbf{}", "strict_json:bom"),
        ("nonfinite", b'{"x":NaN}', "strict_json:value"),
        ("positive_infinity", b'{"x":Infinity}', "strict_json:value"),
        ("literal_lone_surrogate", b'{"x":"\xed\xa0\x80"}', "strict_json:utf8"),
        ("escaped_lone_surrogate", b'{"x":"\\ud800"}', "strict_json:unpaired_surrogate"),
        ("escaped_lone_low_surrogate", b'{"x":"\\udc00"}', "strict_json:unpaired_surrogate"),
        ("truncated_unicode_escape", b'{"x":"\\u123"}', "strict_json:unicode_escape"),
        ("decimal", b'{"x":1.0}', "strict_json:noninteger"),
        ("exponent", b'{"x":1e0}', "strict_json:noninteger"),
        ("negative_zero", b'{"x":-0}', "strict_json:negative_zero"),
        ("above_safe_integer", b'{"x":9007199254740992}', "strict_json:integer_domain"),
        ("below_safe_integer", b'{"x":-9007199254740992}', "strict_json:integer_domain"),
        ("trailing_content", b"{}{}", "strict_json:trailing_content"),
        ("unescaped_control", b'{"x":"\x01"}', "strict_json:unescaped_control"),
    ],
)
def test_strict_reference_rejects_noncanonical_spec_inputs(
    tmp_path: Path,
    case_id: str,
    raw: bytes,
    error_prefix: str,
):
    del case_id
    path = tmp_path / "mutant.json"
    path.write_bytes(raw)

    completed = _run_reference(path)

    assert completed.returncode != 0
    result = _result(completed)
    assert result["valid"] is False
    assert result["error"].startswith(error_prefix)
    assert result["provider_calls_required"] is False
    with pytest.raises(ContractIdentityError):
        load_strict_normalization_spec(path)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"x":-9007199254740991}',
        b'{"x":9007199254740991}',
        b'{"x":"\\ud83d\\ude00"}',
        '{"x":"😀"}'.encode(),
        b'{"outer":{"x":1}}',
    ],
)
def test_both_strict_loaders_accept_valid_boundary_scalars(
    tmp_path: Path,
    raw: bytes,
):
    path = tmp_path / "valid.json"
    path.write_bytes(raw)

    python_result = load_strict_normalization_spec(path)
    completed = _run_reference(path, parse_only=True)

    assert isinstance(python_result, dict)
    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    assert _result(completed) == {
        "valid": True,
        "strict_parse_valid": True,
        "provider_calls_required": False,
    }


def _toggle_boolean(artifact: dict[str, Any]) -> None:
    hash_policy = artifact["specification_identity"]["bootstrap_canonicalization"][
        "hash"
    ]
    hash_policy["hmac"] = not hash_policy["hmac"]


def _change_selected_string(artifact: dict[str, Any]) -> None:
    artifact["raw_response_policy"]["canonical_surface_reason"] += " "


def _change_selected_array(artifact: dict[str, Any]) -> None:
    values = artifact["raw_response_policy"]["forbidden_metadata"]
    values[0], values[1] = values[1], values[0]


def _unicode_scalar_change(artifact: dict[str, Any]) -> None:
    artifact["raw_response_policy"]["canonical_surface_reason"] += "e\u0301"


def _null_to_missing(artifact: dict[str, Any]) -> None:
    del artifact["specification_identity"]["bootstrap_canonicalization"]["hash"][
        "prefix"
    ]


def _registry_expected_hash(artifact: dict[str, Any]) -> None:
    registry = artifact["specification_identity"]["embedded_policy_registry"]
    registry["raw_provider_response_policy_v1"]["expected_semantic_hash"] = "0" * 64


def _cached_child_hash(artifact: dict[str, Any]) -> None:
    cache = artifact["specification_identity"]["derived_hash_cache"][
        "registered_policy_semantic_hashes"
    ]
    cache["raw_provider_response_policy_v1"] = "0" * 64


def _change_child_semantics(artifact: dict[str, Any]) -> None:
    reason = artifact["raw_response_policy"]["canonical_surface_reason"]
    artifact["raw_response_policy"]["canonical_surface_reason"] = reason.replace(
        "HTTP", "canonical HTTP", 1
    )


def _policy_id(artifact: dict[str, Any]) -> None:
    artifact["raw_response_policy"]["policy_id"] = "other_policy_v1"


def _policy_version(artifact: dict[str, Any]) -> None:
    artifact["specification_identity"]["embedded_policy_registry"][
        "canonical_parser_policy_json_v1"
    ]["policy_version"] = "v2"
    artifact["specification_identity"]["bootstrap_canonicalization"][
        "version"
    ] = "v2"


def _pointer_and_location(artifact: dict[str, Any]) -> None:
    artifact["moved_raw_response_policy"] = artifact.pop("raw_response_policy")
    artifact["specification_identity"]["embedded_policy_registry"][
        "raw_provider_response_policy_v1"
    ]["json_pointer"] = "/moved_raw_response_policy"


def _duplicate_policy_identity(artifact: dict[str, Any]) -> None:
    artifact["specification_identity"]["embedded_policy_registry"][
        "raw_provider_response_policy_v1"
    ]["policy_id"] = "strict_json_policy_v1"


def _extra_normative_field(artifact: dict[str, Any]) -> None:
    artifact["raw_response_policy"]["unknown_normative_field"] = True


def _authoritative_cache(artifact: dict[str, Any]) -> None:
    artifact["specification_identity"]["derived_hash_cache"]["authoritative"] = True


def _extra_p1_field(artifact: dict[str, Any]) -> None:
    artifact["p1_resolution_status"]["P1 #9"] = "invented"


def _extra_cache_field(artifact: dict[str, Any]) -> None:
    artifact["specification_identity"]["derived_hash_cache"]["metadata"] = "x"


def _duplicate_exclusion(artifact: dict[str, Any]) -> None:
    exclusions = artifact["specification_identity"][
        "specification_semantic_excluded_json_pointers"
    ]
    exclusions[-1] = exclusions[0]


def _extra_child_exclusion(artifact: dict[str, Any]) -> None:
    artifact["specification_identity"]["child_policy_exact_exclusions"][
        "raw_provider_response_policy_v1"
    ] = ["/purpose"]


def _invalid_registry_hash(artifact: dict[str, Any]) -> None:
    artifact["specification_identity"]["embedded_policy_registry"][
        "raw_provider_response_policy_v1"
    ]["expected_semantic_hash"] = "not-a-hash"


def _missing_registry_field(artifact: dict[str, Any]) -> None:
    del artifact["specification_identity"]["embedded_policy_registry"][
        "raw_provider_response_policy_v1"
    ]["hash_scope"]


def _malformed_registry_pointer(artifact: dict[str, Any]) -> None:
    artifact["specification_identity"]["embedded_policy_registry"][
        "raw_provider_response_policy_v1"
    ]["json_pointer"] = "/raw_response_policy/~2"


MUTATIONS: tuple[
    tuple[str, Callable[[dict[str, Any]], None], str, bool | None, bool | None],
    ...,
] = (
    ("H3", _change_selected_array, "child_hash:registry", True, True),
    ("H4", _change_selected_string, "child_hash:registry", True, True),
    ("H5", _unicode_scalar_change, "child_hash:registry", True, True),
    ("H7", _null_to_missing, "child_hash:registry", True, True),
    ("H8", _toggle_boolean, "child_hash:registry", True, True),
    ("H9", _registry_expected_hash, "child_hash:registry", False, False),
    ("H10", _cached_child_hash, "child_hash:cache", False, False),
    ("H11", _change_child_semantics, "child_hash:registry", True, True),
    ("H14", _policy_id, "registry:subtree_identity", True, True),
    ("H15", _policy_version, "registry:expected_binding", True, True),
    ("H16", _pointer_and_location, "registry:spec_binding", False, True),
    ("H18", _duplicate_policy_identity, "registry:identity_uniqueness", None, None),
    ("H19", _extra_normative_field, "child_hash:registry", True, True),
    ("E1", _cached_child_hash, "child_hash:cache", False, False),
    ("E2", _authoritative_cache, "spec_hash:stale_binding", False, True),
    ("E3", _extra_p1_field, "spec_hash:stale_binding", False, True),
    ("E4", _extra_cache_field, "cache:shape", False, True),
    (
        "closed_spec_exclusions",
        _duplicate_exclusion,
        "exclusions:closed_inventory",
        None,
        None,
    ),
    (
        "closed_child_exclusions",
        _extra_child_exclusion,
        "child_exclusions:shape",
        None,
        None,
    ),
    (
        "invalid_registry_hash",
        _invalid_registry_hash,
        "registry_expected:hash_format",
        False,
        False,
    ),
    (
        "missing_registry_field",
        _missing_registry_field,
        "registry_record:shape",
        None,
        None,
    ),
    (
        "malformed_registry_pointer",
        _malformed_registry_pointer,
        "json_pointer:escape",
        None,
        None,
    ),
)

VALID_RELATIONAL_CASES = ("H1", "H2", "H6", "H17", "H20")
EXTERNAL_RELATIONAL_CASES = ("H12", "H13")


@pytest.mark.parametrize(
    (
        "case_id",
        "mutate",
        "error_prefix",
        "child_hash_changes",
        "spec_hash_changes",
    ),
    MUTATIONS,
)
def test_reference_fails_closed_for_semantic_and_cache_mutations(
    tmp_path: Path,
    case_id: str,
    mutate: Callable[[dict[str, Any]], None],
    error_prefix: str,
    child_hash_changes: bool | None,
    spec_hash_changes: bool | None,
):
    artifact = load_strict_normalization_spec(PARSER_PATH)
    baseline_children, baseline_spec = _identity_snapshot(artifact)
    mutate(artifact)
    if child_hash_changes is not None and spec_hash_changes is not None:
        mutated_children, mutated_spec = _identity_snapshot(artifact)
        mutated_spec_bytes, mutated_child_bytes = _expected_canonical_bytes(artifact)
        assert (mutated_children != baseline_children) is child_hash_changes
        assert (mutated_spec != baseline_spec) is spec_hash_changes
    path = tmp_path / "mutant.json"
    _write_artifact(path, artifact)
    assert hashlib.sha256(path.read_bytes()).hexdigest() != SPEC_FILE_HASH

    completed = _run_reference(path, analyze=True, include_canonical=True)

    result = _result(completed)
    if case_id in {
        "H18",
        "E4",
        "closed_spec_exclusions",
        "closed_child_exclusions",
        "missing_registry_field",
        "malformed_registry_pointer",
    }:
        assert completed.returncode != 0
    else:
        assert completed.returncode == 0, completed.stderr
        assert result["preflight_valid"] is False
        assert (result["child_hashes"] != baseline_children) is child_hash_changes
        assert (
            result["normalization_spec_semantic_hash"] != baseline_spec
        ) is spec_hash_changes
        assert base64.b64decode(
            result["normalization_spec_canonical_base64"]
        ) == mutated_spec_bytes
        assert {
            policy_id: base64.b64decode(encoded)
            for policy_id, encoded in result["child_canonical_base64"].items()
        } == mutated_child_bytes
    assert result["error"].startswith(error_prefix)
    assert result["provider_calls_required"] is False
    with pytest.raises(ContractIdentityError):
        verify_normalization_parser_artifact(artifact)


@pytest.mark.parametrize("case_id", VALID_RELATIONAL_CASES)
def test_reference_preserves_identity_for_frozen_nonsemantic_mutations(
    tmp_path: Path,
    case_id: str,
):
    artifact = load_strict_normalization_spec(PARSER_PATH)
    baseline_children, baseline_spec = _identity_snapshot(artifact)
    path = tmp_path / "mutant.json"
    if case_id == "H1":
        _write_artifact(path, artifact, separators=(",", ":"), indent=None)
    elif case_id == "H2":
        reordered = {key: artifact[key] for key in reversed(tuple(artifact))}
        _write_artifact(path, reordered)
    elif case_id == "H6":
        _write_artifact(path, artifact, ensure_ascii=True)
    elif case_id == "H17":
        raw = PARSER_PATH.read_bytes()
        path.write_bytes(raw[:-1] if raw.endswith(b"\n") else raw + b"\n")
    else:
        artifact["provider_calls_completed"] += 1
        _write_artifact(path, artifact)

    completed = _run_reference(path, include_canonical=True)
    mutated_artifact = load_strict_normalization_spec(path)
    python_identity = verify_normalization_parser_artifact(mutated_artifact)

    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    result = _result(completed)
    assert result["valid"] is True
    assert result["normalization_spec_file_sha256"] != SPEC_FILE_HASH
    assert result["normalization_spec_semantic_hash"] == SPEC_HASH
    assert result["normalization_spec_semantic_hash"] == baseline_spec
    assert result["child_hashes"] == baseline_children
    assert result["normalization_spec_semantic_hash"] == python_identity.semantic_hash
    assert result["child_hashes"] == dict(python_identity.child_hashes)
    spec_bytes, child_bytes = _expected_canonical_bytes(mutated_artifact)
    assert base64.b64decode(result["normalization_spec_canonical_base64"]) == spec_bytes
    assert {
        policy_id: base64.b64decode(encoded)
        for policy_id, encoded in result["child_canonical_base64"].items()
    } == child_bytes
    assert result["provider_calls_required"] is False


def test_reference_does_not_normalize_composed_and_decomposed_unicode(
    tmp_path: Path,
):
    artifact = load_strict_normalization_spec(PARSER_PATH)
    original = artifact["raw_response_policy"]["canonical_surface_reason"]
    composed = copy.deepcopy(artifact)
    decomposed = copy.deepcopy(artifact)
    composed["raw_response_policy"]["canonical_surface_reason"] = (
        original.replace("e", "é", 1)
    )
    decomposed["raw_response_policy"]["canonical_surface_reason"] = (
        original.replace("e", "e\u0301", 1)
    )
    composed_path = tmp_path / "composed.json"
    decomposed_path = tmp_path / "decomposed.json"
    _write_artifact(composed_path, composed)
    _write_artifact(decomposed_path, decomposed)

    left = _run_reference(composed_path)
    right = _run_reference(decomposed_path)

    assert left.returncode != 0
    assert right.returncode != 0
    assert _result(left)["error"].startswith("child_hash:registry")
    assert _result(right)["error"].startswith("child_hash:registry")
    assert composed_path.read_bytes() != decomposed_path.read_bytes()
    assert _canonical_bytes(composed) != _canonical_bytes(decomposed)


@pytest.mark.parametrize(
    ("case_id", "field"),
    [
        ("H12", "prompt_template_set_hash"),
        ("H13", "output_schema_set_hash"),
    ],
)
def test_both_preflights_reject_mutated_external_contract_bindings(
    tmp_path: Path,
    case_id: str,
    field: str,
):
    del case_id
    artifact = load_strict_normalization_spec(PARSER_PATH)
    baseline_children, baseline_spec = _identity_snapshot(artifact)
    artifact["frozen_references"][field] = "0" * 64
    expected_field = f"{field}_expected"
    artifact["specification_identity"]["external_dependency_hashes"][
        expected_field
    ] = "0" * 64
    mutated_children, mutated_spec = _identity_snapshot(artifact)
    mutated_spec_bytes, mutated_child_bytes = _expected_canonical_bytes(artifact)
    artifact["specification_identity"]["derived_hash_cache"][
        "normalization_spec_semantic_hash"
    ] = mutated_spec
    path = tmp_path / "external-binding-mutant.json"
    _write_artifact(path, artifact)
    assert hashlib.sha256(path.read_bytes()).hexdigest() != SPEC_FILE_HASH

    completed = _run_reference(
        path,
        authorized_spec_hash=mutated_spec,
        analyze=True,
        include_canonical=True,
    )

    assert completed.returncode == 0, completed.stderr
    result = _result(completed)
    assert result["valid"] is False
    assert result["preflight_valid"] is False
    assert result["error"] == "external_binding:artifact"
    assert result["child_hashes"] == baseline_children == mutated_children
    assert result["normalization_spec_semantic_hash"] == mutated_spec
    assert base64.b64decode(
        result["normalization_spec_canonical_base64"]
    ) == mutated_spec_bytes
    assert {
        policy_id: base64.b64decode(encoded)
        for policy_id, encoded in result["child_canonical_base64"].items()
    } == mutated_child_bytes
    assert mutated_spec != baseline_spec
    assert result["provider_calls_required"] is False

    python_identity = verify_normalization_parser_artifact(artifact)
    assert python_identity.semantic_hash == mutated_spec
    actual_prompt_hash = verify_prompt_template_artifact(
        load_strict_contract_json(PROMPT_PATH)
    ).set_hash
    actual_schema_hash = verify_output_schema_artifact(
        load_strict_contract_json(SCHEMA_PATH)
    ).set_hash
    assert (
        artifact["frozen_references"]["prompt_template_set_hash"]
        != actual_prompt_hash
        or artifact["frozen_references"]["output_schema_set_hash"]
        != actual_schema_hash
    )


def test_frozen_hash_conformance_inventory_is_complete():
    artifact = load_strict_normalization_spec(PARSER_PATH)
    declared = artifact["specification_identity"]["hash_conformance_test_vectors"]
    primary = [record["id"] for record in declared["relational_vectors"]]
    exclusion = [
        record["id"] for record in declared["exclusion_escape_vectors"]["vectors"]
    ]

    assert primary == [f"H{number}" for number in range(1, 21)]
    assert exclusion == [f"E{number}" for number in range(1, 5)]
    executable_primary = {
        case_id for case_id, *_unused in MUTATIONS if case_id.startswith("H")
    } | set(VALID_RELATIONAL_CASES) | set(EXTERNAL_RELATIONAL_CASES)
    executable_exclusion = {
        case_id for case_id, *_unused in MUTATIONS if case_id.startswith("E")
    }
    assert executable_primary == set(primary)
    assert executable_exclusion == set(exclusion)
    declared_relations = {
        record["id"]: (
            record["child_hash_changes"],
            record["spec_hash_changes"],
        )
        for record in declared["relational_vectors"]
    }
    tested_relations = {
        case_id: (child_changes, spec_changes)
        for case_id, _mutate, _error, child_changes, spec_changes in MUTATIONS
        if case_id.startswith("H")
    }
    tested_relations.update(
        {case_id: (False, False) for case_id in VALID_RELATIONAL_CASES}
    )
    tested_relations.update(
        {case_id: (False, True) for case_id in EXTERNAL_RELATIONAL_CASES}
    )
    assert tested_relations == declared_relations
    assert all(
        record["file_hash_changes"] is True
        for record in declared["relational_vectors"]
    )
    declared_exclusion_relations = {
        record["id"]: (
            record["child_hash_changes"],
            record["spec_hash_changes"],
        )
        for record in declared["exclusion_escape_vectors"]["vectors"]
    }
    tested_exclusion_relations = {
        case_id: (child_changes, spec_changes)
        for case_id, _mutate, _error, child_changes, spec_changes in MUTATIONS
        if case_id.startswith("E")
    }
    assert tested_exclusion_relations == declared_exclusion_relations
    assert all(
        record["file_hash_changes"] is True
        for record in declared["exclusion_escape_vectors"]["vectors"]
    )
    assert hashlib.sha256(PARSER_PATH.read_bytes()).hexdigest() == SPEC_FILE_HASH
