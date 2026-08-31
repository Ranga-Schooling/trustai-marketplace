"""Executable conformance boundary for the frozen URL-security policy.

The policy artifact is the sole vector truth source.  These tests deliberately
do not contain an implementation: the parameterized cases remain RED until
``app.services.url_security.validate_url_security`` exists.
"""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
import socket
import sys
import urllib.request

import pytest


pytestmark = pytest.mark.contract

POLICY_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "testing"
    / "ai-evaluation"
    / "url-security-policy.v1.json"
)
POLICY_ID = "url_security_policy_v1"
POLICY_VERSION = "v1"
POLICY_SEMANTIC_HASH = (
    "fcc37b299f84cccb7522c2db150022e3e92f04430c50e01b94bb7f7fa6e5b44e"
)
VALIDATOR_MODULE = "app.services.url_security"
VALIDATOR_NAME = "validate_url_security"

INPUT_KEYS = (
    "exact_url",
    "url_role",
    "retrieval_auth_context",
    "redirect_context",
    "origin_rule",
    "restricted_trace_reference",
)
OUTPUT_KEYS = (
    "classification",
    "reason_codes",
    "url_role",
    "restricted_trace_reference",
    "policy_id",
    "policy_version",
    "policy_hash",
)
EXPECTED_VECTOR_KEYS = (
    "classification",
    "reason_codes",
    "safe_canonical_url_may_exist",
    "parser_consequence",
    "origin_identity",
    "redirect_loop_identity",
    "context_loop_detected",
)
CLASSIFICATIONS = ("public_safe", "sensitive", "indeterminate")
REASON_CODES = (
    "userinfo_present",
    "recognized_sensitive_query_material",
    "signed_url_detected",
    "authenticated_context",
    "sensitive_redirect_context",
    "public_shareability_indeterminate",
)
VECTOR_GROUP_KEYS = (
    "existing_direct",
    "existing_redirect",
    "existing_propagation_and_privacy",
    "existing_positive_proof",
    "adversarial",
)


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value):
    raise ValueError(f"Non-finite JSON number: {value}")


def _load_policy() -> dict:
    return json.loads(
        POLICY_PATH.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_nonfinite,
    )


POLICY = _load_policy()
VECTORS = tuple(
    vector
    for group_key in VECTOR_GROUP_KEYS
    for vector in POLICY["test_vectors"][group_key]
)
INVOCATION_VECTORS = tuple(vector for vector in VECTORS if vector["id"] != "UP8")


def _remove_json_pointer(document: dict, pointer: str) -> None:
    parts = [part.replace("~1", "/").replace("~0", "~") for part in pointer.split("/")[1:]]
    target = document
    for part in parts[:-1]:
        target = target[part]
    del target[parts[-1]]


def _semantic_hash(policy: dict) -> str:
    identity = policy["specification_identity"]
    semantic_identity = identity["semantic_identity"]
    content = copy.deepcopy(policy)
    for pointer in semantic_identity["semantic_excluded_json_pointers"]:
        _remove_json_pointer(content, pointer)
    envelope = {
        "identity_domain": semantic_identity["identity_domain"],
        "policy_id": identity["policy_id"],
        "policy_version": identity["policy_version"],
        "content": content,
    }
    canonical_bytes = json.dumps(
        envelope,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


def _vector_id(vector: dict) -> str:
    return f'{vector["group"]}:{vector["id"]}:{vector["focus"]}'


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network(*_args, **_kwargs):
        pytest.fail("URL-security validation attempted external access", pytrace=False)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(socket, "getaddrinfo", fail_network)
    monkeypatch.setattr(socket.socket, "connect", fail_network)
    monkeypatch.setattr(socket.socket, "connect_ex", fail_network)
    monkeypatch.setattr(urllib.request, "urlopen", fail_network)

    original_getenv = os.getenv

    def guarded_getenv(key, default=None):
        if any(token in key.upper() for token in ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")):
            pytest.fail(
                f"URL-security validation attempted secret environment discovery: {key}",
                pytrace=False,
            )
        return original_getenv(key, default)

    monkeypatch.setattr(os, "getenv", guarded_getenv)


def _load_validator():
    try:
        module = importlib.import_module(VALIDATOR_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name == VALIDATOR_MODULE:
            pytest.fail(
                "Missing URL-security validator implementation: expected "
                f"{VALIDATOR_MODULE}.{VALIDATOR_NAME}",
                pytrace=False,
            )
        raise
    validator = getattr(module, VALIDATOR_NAME, None)
    if not callable(validator):
        pytest.fail(
            "Missing URL-security validator callable: expected "
            f"{VALIDATOR_MODULE}.{VALIDATOR_NAME}",
            pytrace=False,
        )
    return validator


def _classifier_input(vector_id: str) -> dict:
    vector = next(vector for vector in VECTORS if vector["id"] == vector_id)
    return copy.deepcopy(vector["classifier_input"])


def _invoke_validator(classifier_input: dict, monkeypatch: pytest.MonkeyPatch):
    _deny_external_access(monkeypatch)
    return _load_validator()(**classifier_input)


def _assert_safe_indeterminate(result: Mapping, classifier_input: dict) -> None:
    assert result == {
        "classification": "indeterminate",
        "reason_codes": ["public_shareability_indeterminate"],
        "url_role": classifier_input["url_role"],
        "restricted_trace_reference": classifier_input["restricted_trace_reference"],
        "policy_id": POLICY_ID,
        "policy_version": POLICY_VERSION,
        "policy_hash": POLICY_SEMANTIC_HASH,
    }
    assert classifier_input["exact_url"] not in result.values()


def _recompute_origin_rule_hash(origin_rule: dict) -> None:
    content = copy.deepcopy(origin_rule)
    content.pop("rule_hash")
    envelope = {
        "identity_domain": "trustai.url_origin_rule.v1",
        "rule_id": origin_rule["rule_id"],
        "rule_version": origin_rule["rule_version"],
        "content": content,
    }
    canonical_bytes = json.dumps(
        envelope,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    origin_rule["rule_hash"] = hashlib.sha256(canonical_bytes).hexdigest()


def test_policy_identity_and_semantic_hash_are_frozen():
    identity = POLICY["specification_identity"]

    assert identity["policy_id"] == POLICY_ID
    assert identity["policy_version"] == POLICY_VERSION
    assert _semantic_hash(POLICY) == POLICY_SEMANTIC_HASH
    assert identity["derived_hash_cache"]["policy_semantic_hash"] == POLICY_SEMANTIC_HASH
    assert identity["derived_hash_cache"]["authoritative"] is False
    assert identity["semantic_identity"]["recomputation_authoritative"] is True


def test_vector_invocation_and_up8_inventory_is_frozen():
    ids = [vector["id"] for vector in VECTORS]
    up8 = [vector for vector in VECTORS if vector["id"] == "UP8"]

    assert len(VECTORS) == 143
    assert len(ids) == len(set(ids))
    assert len(INVOCATION_VECTORS) == 142
    assert len(up8) == 1
    assert up8[0]["vector_kind"] == "topology_preflight_non_invocation"
    assert set(up8[0]["classifier_input_slots"]) == set(INPUT_KEYS)
    assert all(value is None for value in up8[0]["classifier_input_slots"].values())
    assert up8[0]["expected"]["classifier_invoked"] is False


def test_classifier_input_and_output_contracts_are_exact():
    interface = POLICY["classifier_interface"]

    assert tuple(interface["input_exact_keys"]) == INPUT_KEYS
    assert tuple(interface["inputs"]) == INPUT_KEYS
    assert tuple(interface["output_exact_keys"]) == OUTPUT_KEYS
    assert all(set(vector["classifier_input"]) == set(INPUT_KEYS) for vector in INVOCATION_VECTORS)


def test_frozen_vector_expectations_are_complete():
    assert tuple(POLICY["test_vectors"]["schema"]["expected_exact_keys"]) == EXPECTED_VECTOR_KEYS
    assert all(set(vector["expected"]) == set(EXPECTED_VECTOR_KEYS) for vector in INVOCATION_VECTORS)


def test_classifications_reason_codes_and_cardinality_are_closed():
    vocabularies = POLICY["closed_vocabularies"]

    assert tuple(vocabularies["classification"]) == CLASSIFICATIONS
    assert tuple(vocabularies["reason_codes"]) == REASON_CODES
    assert {
        reason
        for vector in INVOCATION_VECTORS
        for reason in vector["expected"]["reason_codes"]
    } == set(REASON_CODES)
    for vector in INVOCATION_VECTORS:
        expected = vector["expected"]
        assert expected["classification"] in CLASSIFICATIONS
        expected_count = 0 if expected["classification"] == "public_safe" else 1
        assert len(expected["reason_codes"]) == expected_count


def test_high_value_diagnostic_categories_are_covered():
    groups = {vector["group"] for vector in VECTORS}
    category_groups = {
        "ports": {"port"},
        "host_ip": {"host_ip", "host_family_completion", "ipv6_completion"},
        "userinfo": {"userinfo_completion"},
        "path": {"path", "path_completion"},
        "query": {"query", "query_completion"},
        "fragment": {"fragment"},
        "malformed": {"malformed", "authority_scheme"},
        "precedence": {"precedence"},
        "redirects": {"redirect", "redirect_adversarial", "redirect_completion"},
        "positive_proof": {"positive_proof"},
        "propagation_privacy": {"propagation_and_privacy"},
    }

    assert all(expected_groups & groups for expected_groups in category_groups.values())


def test_downstream_vector_expectations_are_well_formed():
    origin_keys = {"scheme", "host_kind", "host", "effective_port"}
    loop_keys = {
        "origin_identity",
        "path",
        "query_present",
        "query",
        "fragment_present",
        "fragment",
    }

    for vector in INVOCATION_VECTORS:
        expected = vector["expected"]
        is_public = expected["classification"] == "public_safe"
        assert expected["safe_canonical_url_may_exist"] is is_public
        assert expected["parser_consequence"] == (
            "accepted" if is_public else "failed_url_security_validation"
        )
        if expected["origin_identity"] is not None:
            assert set(expected["origin_identity"]) == origin_keys
        if expected["redirect_loop_identity"] is not None:
            assert set(expected["redirect_loop_identity"]) == loop_keys
            assert set(expected["redirect_loop_identity"]["origin_identity"]) == origin_keys


def test_security_invariants_are_explicit_in_frozen_vectors():
    by_id = {vector["id"]: vector for vector in VECTORS}

    assert by_id["UP1"]["expected"]["safe_canonical_url_may_exist"] is False
    assert by_id["UP3"]["expected"]["safe_canonical_url_may_exist"] is False
    assert by_id["UP4"]["expected"]["classification"] == "sensitive"
    assert by_id["PP1"]["expected"]["classification"] == "indeterminate"
    assert by_id["PP2"]["expected"]["classification"] == "indeterminate"
    assert by_id["PP3"]["expected"]["classification"] == "indeterminate"
    assert by_id["PP4"]["expected"]["classification"] == "indeterminate"
    assert by_id["PP5"]["expected"]["classification"] == "public_safe"
    assert POLICY["failure_propagation"]["sanitized_continuation_allowed"] is False
    assert POLICY["public_safe_rule"]["provider_or_model_claim_sufficient"] is False


def test_regression_huge_port_returns_safe_indeterminate(monkeypatch):
    classifier_input = _classifier_input("D7")
    exact_url = f'https://catalog.public.example:{"9" * 5000}/product/widget'
    classifier_input["exact_url"] = exact_url
    classifier_input["origin_rule"] = {"status": "missing"}
    classifier_input["redirect_context"]["members"][0].update(
        exact_url=exact_url,
        origin_rule={"status": "missing"},
    )

    result = _invoke_validator(classifier_input, monkeypatch)

    _assert_safe_indeterminate(result, classifier_input)


def test_regression_huge_ipv4_octet_returns_safe_indeterminate(monkeypatch):
    classifier_input = _classifier_input("D7")
    exact_url = f'https://{"9" * 5000}.1.1.1/product/widget'
    classifier_input["exact_url"] = exact_url
    classifier_input["origin_rule"] = {"status": "missing"}
    classifier_input["redirect_context"]["members"][0].update(
        exact_url=exact_url,
        origin_rule={"status": "missing"},
    )

    result = _invoke_validator(classifier_input, monkeypatch)

    _assert_safe_indeterminate(result, classifier_input)


def test_regression_string_current_position_returns_safe_indeterminate(monkeypatch):
    classifier_input = _classifier_input("R1")
    classifier_input["redirect_context"]["current_position"] = "1"

    result = _invoke_validator(classifier_input, monkeypatch)

    _assert_safe_indeterminate(result, classifier_input)


def test_regression_unpaired_surrogate_rule_returns_safe_indeterminate(monkeypatch):
    classifier_input = _classifier_input("D7")
    classifier_input["origin_rule"]["rule_id"] = "invalid-\ud800-rule"
    classifier_input["redirect_context"]["members"][0]["origin_rule"] = copy.deepcopy(
        classifier_input["origin_rule"]
    )

    result = _invoke_validator(classifier_input, monkeypatch)

    _assert_safe_indeterminate(result, classifier_input)


def test_regression_deep_rule_returns_safe_indeterminate(monkeypatch):
    classifier_input = _classifier_input("D7")
    nested = {}
    cursor = nested
    for _ in range(sys.getrecursionlimit() + 50):
        cursor["nested"] = {}
        cursor = cursor["nested"]
    malformed_rule = {"status": "missing", "extra": nested}
    classifier_input["origin_rule"] = malformed_rule
    classifier_input["redirect_context"]["members"][0]["origin_rule"] = malformed_rule

    result = _invoke_validator(classifier_input, monkeypatch)

    _assert_safe_indeterminate(result, classifier_input)


def test_regression_alternate_ipv4_cannot_match_dns_positive_rule(monkeypatch):
    classifier_input = _classifier_input("D7")
    exact_url = "https://127.1/product/widget?id=123&utm_source=search"
    classifier_input["exact_url"] = exact_url
    classifier_input["origin_rule"]["origin_identity"].update(
        host_kind="dns",
        host="127.1",
    )
    _recompute_origin_rule_hash(classifier_input["origin_rule"])
    classifier_input["redirect_context"]["members"][0].update(
        exact_url=exact_url,
        origin_rule=copy.deepcopy(classifier_input["origin_rule"]),
    )

    result = _invoke_validator(classifier_input, monkeypatch)

    _assert_safe_indeterminate(result, classifier_input)


def test_regression_noncurrent_indeterminate_redirect_member_fails_chain(monkeypatch):
    classifier_input = _classifier_input("R1")
    classifier_input["redirect_context"]["members"][0]["origin_rule"] = {
        "status": "missing"
    }

    result = _invoke_validator(classifier_input, monkeypatch)

    _assert_safe_indeterminate(result, classifier_input)


def test_regression_wrong_origin_rule_hash_fails_closed(monkeypatch):
    classifier_input = _classifier_input("D7")
    classifier_input["origin_rule"]["rule_hash"] = "0" * 64
    classifier_input["redirect_context"]["members"][0]["origin_rule"]["rule_hash"] = (
        "0" * 64
    )

    result = _invoke_validator(classifier_input, monkeypatch)

    _assert_safe_indeterminate(result, classifier_input)


def test_regression_userinfo_outranks_signed_url(monkeypatch):
    classifier_input = _classifier_input("D7")
    exact_url = (
        "https://synthetic-user@catalog.public.example/product/widget"
        "?X-Amz-Signature=SYNTHETIC-NON-SECRET"
    )
    classifier_input.update(
        exact_url=exact_url,
        origin_rule={"status": "missing"},
    )
    classifier_input["redirect_context"]["members"][0].update(
        exact_url=exact_url,
        origin_rule={"status": "missing"},
    )

    result = _invoke_validator(classifier_input, monkeypatch)

    assert result == {
        "classification": "sensitive",
        "reason_codes": ["userinfo_present"],
        "url_role": classifier_input["url_role"],
        "restricted_trace_reference": classifier_input["restricted_trace_reference"],
        "policy_id": POLICY_ID,
        "policy_version": POLICY_VERSION,
        "policy_hash": POLICY_SEMANTIC_HASH,
    }


def test_regression_sensitive_redirect_outranks_current_recognized_material(monkeypatch):
    classifier_input = _classifier_input("R1")
    requested_url = (
        "https://a.public.example/reset-password/SYNTHETIC-NON-SECRET"
    )
    current_url = (
        "https://b.public.example/product/two?token=SYNTHETIC-NON-SECRET"
    )
    classifier_input.update(
        exact_url=current_url,
        origin_rule={"status": "missing"},
    )
    classifier_input["redirect_context"]["members"][0].update(
        exact_url=requested_url,
        origin_rule={"status": "missing"},
    )
    classifier_input["redirect_context"]["members"][1].update(
        exact_url=current_url,
        origin_rule={"status": "missing"},
    )

    result = _invoke_validator(classifier_input, monkeypatch)

    assert result == {
        "classification": "sensitive",
        "reason_codes": ["sensitive_redirect_context"],
        "url_role": classifier_input["url_role"],
        "restricted_trace_reference": classifier_input["restricted_trace_reference"],
        "policy_id": POLICY_ID,
        "policy_version": POLICY_VERSION,
        "policy_hash": POLICY_SEMANTIC_HASH,
    }


@pytest.mark.parametrize("vector", INVOCATION_VECTORS, ids=_vector_id)
def test_validator_matches_frozen_vector(vector, monkeypatch):
    _deny_external_access(monkeypatch)
    validator = _load_validator()

    result = validator(**vector["classifier_input"])

    assert isinstance(result, Mapping)
    assert set(result) == set(OUTPUT_KEYS)
    assert result == {
        "classification": vector["expected"]["classification"],
        "reason_codes": vector["expected"]["reason_codes"],
        "url_role": vector["classifier_input"]["url_role"],
        "restricted_trace_reference": vector["classifier_input"]["restricted_trace_reference"],
        "policy_id": POLICY_ID,
        "policy_version": POLICY_VERSION,
        "policy_hash": POLICY_SEMANTIC_HASH,
    }
    assert result["restricted_trace_reference"] == vector["classifier_input"][
        "restricted_trace_reference"
    ]
    assert vector["classifier_input"]["exact_url"] not in result.values()
