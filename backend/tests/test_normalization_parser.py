"""Executable boundary for the frozen normalization-parser raw hash.

The committed parser artifact is the semantic authority.  Structural tests
remain useful before implementation exists; functional cases deliberately use
a deferred import so the initial RED result identifies only the missing
``hash_raw_provider_response`` callable.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
from pathlib import Path
import socket
import urllib.request

import pytest


pytestmark = pytest.mark.contract

SPEC_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "testing"
    / "ai-evaluation"
    / "normalization-parser.v1.json"
)
SPEC_ID = "normalization_parser_spec_v1"
SPEC_VERSION = "v1"
HASHER_MODULE = "app.services.normalization_parser"
HASHER_NAME = "hash_raw_provider_response"
EMPTY_SHA256 = (
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
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


def _load_spec() -> dict:
    return json.loads(
        SPEC_PATH.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_nonfinite,
    )


SPEC = _load_spec()
RAW_HASH_VECTORS = tuple(SPEC["raw_hash_nullability_test_vectors"]["cases"])
TRANSPORT_VECTORS = tuple(SPEC["transport_boundary_test_vectors"]["cases"])


def _load_hasher():
    try:
        module = importlib.import_module(HASHER_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name == HASHER_MODULE:
            pytest.fail(
                "Missing raw-response hash implementation: expected "
                f"{HASHER_MODULE}.{HASHER_NAME}",
                pytrace=False,
            )
        raise
    hasher = getattr(module, HASHER_NAME, None)
    if not callable(hasher):
        pytest.fail(
            "Missing raw-response hash callable: expected "
            f"{HASHER_MODULE}.{HASHER_NAME}",
            pytrace=False,
        )
    return hasher


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network(*_args, **_kwargs):
        pytest.fail("Raw-response hashing attempted external access", pytrace=False)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(socket, "getaddrinfo", fail_network)
    monkeypatch.setattr(socket.socket, "connect", fail_network)
    monkeypatch.setattr(socket.socket, "connect_ex", fail_network)
    monkeypatch.setattr(urllib.request, "urlopen", fail_network)

    original_getenv = os.getenv

    def guarded_getenv(key, default=None):
        if any(
            token in key.upper()
            for token in ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
        ):
            pytest.fail(
                f"Raw-response hashing attempted secret environment discovery: {key}",
                pytrace=False,
            )
        return original_getenv(key, default)

    monkeypatch.setattr(os, "getenv", guarded_getenv)


def _invoke_hasher(raw_response: bytes, monkeypatch: pytest.MonkeyPatch) -> str:
    _deny_external_access(monkeypatch)
    hasher = _load_hasher()
    return hasher(raw_response)


def test_raw_response_hash_policy_identity_is_frozen():
    raw_policy = SPEC["raw_response_policy"]
    hashing_policy = SPEC["hashing_policy"]

    assert SPEC["artifact_id"] == SPEC_ID
    assert SPEC["normalization_spec_version"] == SPEC_VERSION
    assert SPEC["provider_neutral"] is True
    assert raw_policy["hash_algorithm"] == "SHA-256"
    assert raw_policy["canonical_raw_hash"] == "SHA-256 of raw_provider_response"
    assert hashing_policy["algorithm"] == "SHA-256"
    assert hashing_policy["encoding"] == "lowercase hexadecimal"
    assert hashing_policy["hashes"]["raw_provider_response_hash"]["input"].startswith(
        "exact raw_provider_response:"
    )


def test_raw_hash_vector_inventory_is_frozen():
    vector_set = SPEC["raw_hash_nullability_test_vectors"]
    ids = [vector["id"] for vector in RAW_HASH_VECTORS]

    assert vector_set["test_vector_set_id"] == "raw_hash_nullability_vectors_v1"
    assert vector_set["provider_calls_required"] is False
    assert vector_set["expected_case_count"] == 10
    assert len(RAW_HASH_VECTORS) == 10
    assert ids == [f"RH{number}" for number in range(1, 11)]
    assert len(ids) == len(set(ids))


def test_transport_boundary_inventory_supports_raw_hash_contract():
    vector_set = SPEC["transport_boundary_test_vectors"]
    by_id = {vector["id"]: vector for vector in TRANSPORT_VECTORS}

    assert vector_set["test_vector_set_id"] == "transport_to_semantic_boundary_vectors_v1"
    assert vector_set["provider_calls_required"] is False
    assert vector_set["expected_case_count"] == 14
    assert len(TRANSPORT_VECTORS) == 14
    assert len(by_id) == 14
    assert "raw_provider_response_hash are identical" in by_id["T1"]["expected"]
    assert "raw_provider_response_hash matches" in by_id["T2"]["expected"]
    assert "raw_provider_response_hash are identical" in by_id["T3"]["expected"]
    assert by_id["T11"]["expected"] == "failed_strict_parse"
    assert by_id["T12"]["expected"] == "failed_strict_parse"


def test_empty_body_vector_freezes_sha256_digest():
    rh2 = next(vector for vector in RAW_HASH_VECTORS if vector["id"] == "RH2")

    assert "zero-length byte sequence" in rh2["case"]
    assert EMPTY_SHA256 in rh2["expected"]
    assert "raw_provider_response_hash is required" in rh2["expected"]


EXACT_BYTE_CASES = (
    pytest.param(b"", EMPTY_SHA256, id="empty-rh2"),
    pytest.param(b"a", hashlib.sha256(b"a").hexdigest(), id="ascii-byte"),
    pytest.param(b"\x00", hashlib.sha256(b"\x00").hexdigest(), id="nul-byte"),
    pytest.param(b"\xff", hashlib.sha256(b"\xff").hexdigest(), id="non-utf8-byte"),
    pytest.param(
        b"\xef\xbf\xbd",
        hashlib.sha256(b"\xef\xbf\xbd").hexdigest(),
        id="utf8-replacement-character-bytes",
    ),
    pytest.param(
        "café".encode("utf-8"),
        hashlib.sha256("café".encode("utf-8")).hexdigest(),
        id="utf8-textual-bytes",
    ),
)


@pytest.mark.parametrize(("raw_response", "expected_digest"), EXACT_BYTE_CASES)
def test_hash_raw_provider_response_hashes_exact_bytes(
    raw_response,
    expected_digest,
    monkeypatch,
):
    result = _invoke_hasher(raw_response, monkeypatch)

    assert result == expected_digest
    assert len(result) == 64
    assert result == result.lower()
    assert set(result) <= set("0123456789abcdef")


def test_hash_raw_provider_response_does_not_silently_encode_text(monkeypatch):
    _deny_external_access(monkeypatch)
    hasher = _load_hasher()

    with pytest.raises(TypeError):
        hasher("a")
