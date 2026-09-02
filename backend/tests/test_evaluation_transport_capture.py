"""Provider-neutral tests for bounded canonical transport byte capture."""

from __future__ import annotations

import hashlib

import pytest

from app.services.evaluation_resource_limits import (
    RESOURCE_LIMIT_VALUES,
    ResourceLimitExceededError,
    account_extracted_semantic_chunk,
)
from app.services.evaluation_transport_capture import (
    RESPONSE_TRANSPORT_MODES,
    CanonicalRawResponseAccumulator,
    ExtractedSemanticAccumulator,
    RawResponseCapture,
    TransportCaptureStateError,
    TransportExtractionError,
)
from app.services.normalization_parser import (
    StrictJsonSyntaxError,
    parse_strict_json_payload,
)


EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def _capture_stream(fragments: tuple[bytes, ...]):
    capture = CanonicalRawResponseAccumulator("streaming")
    for fragment in fragments:
        capture.append(fragment)
    return capture.finish_stream(documented_terminal_complete=True)


def test_response_transport_mode_enum_matches_frozen_contract():
    assert RESPONSE_TRANSPORT_MODES == (
        "non_streaming_http",
        "streaming",
        "sdk_native_structured",
    )


def test_t3_network_chunk_boundaries_do_not_change_stream_identity():
    one = _capture_stream((b'{"risk":', b'"low"}'))
    two = _capture_stream((b"{", b'"risk":"low"', b"}"))

    assert one == two
    assert one.raw_provider_response == b'{"risk":"low"}'
    assert one.raw_provider_response_hash == hashlib.sha256(
        b'{"risk":"low"}'
    ).hexdigest()


def test_t4_and_rh10_incomplete_stream_never_promote_partial_prefix(monkeypatch):
    capture = CanonicalRawResponseAccumulator("streaming")
    capture.append(b'{"syntactically":"valid"}')
    monkeypatch.setattr(
        hashlib,
        "sha256",
        lambda *_args, **_kwargs: pytest.fail("partial stream was hashed"),
    )

    result = capture.finish_stream(documented_terminal_complete=False)

    assert result.raw_provider_response is None
    assert result.raw_provider_response_hash is None
    assert result.canonical_raw_byte_availability is False
    assert capture.accumulated_bytes == 0


def test_completed_zero_length_stream_is_transport_extraction_failure():
    capture = CanonicalRawResponseAccumulator("streaming")

    with pytest.raises(TransportExtractionError) as caught:
        capture.finish_stream(documented_terminal_complete=True)

    assert caught.value.category == "failed_transport_extraction"


def test_t10_rh6_and_rh7_absent_response_has_no_fabricated_raw_identity():
    capture = CanonicalRawResponseAccumulator(
        "non_streaming_http",
        canonical_surface_available=False,
    )

    result = capture.finish_response()

    assert result.raw_provider_response is None
    assert result.raw_provider_response_hash is None
    assert result.canonical_raw_byte_availability is False


def test_t11_and_rh2_present_zero_length_body_has_empty_sha_and_parse_failure():
    capture = CanonicalRawResponseAccumulator("non_streaming_http")
    result = capture.finish_response()

    assert result.raw_provider_response == b""
    assert result.raw_provider_response_hash == EMPTY_SHA256
    assert result.canonical_raw_byte_availability is True
    with pytest.raises(StrictJsonSyntaxError):
        parse_strict_json_payload(result.raw_provider_response)


def test_t12_and_rh3_whitespace_body_is_hashed_before_strict_parse_failure():
    capture = CanonicalRawResponseAccumulator("non_streaming_http")
    capture.append(b" \t\r\n")
    result = capture.finish_response()

    assert result.raw_provider_response_hash == hashlib.sha256(b" \t\r\n").hexdigest()
    with pytest.raises(StrictJsonSyntaxError):
        parse_strict_json_payload(result.raw_provider_response)


def test_rh1_non_streaming_exact_body_bytes_are_preserved_and_hashed():
    capture = CanonicalRawResponseAccumulator("non_streaming_http")
    capture.append(b"{")
    capture.append(b"}")

    result = capture.finish_response()

    assert result.raw_provider_response == b"{}"
    assert result.raw_provider_response_hash == hashlib.sha256(b"{}").hexdigest()


def test_rh8_sdk_native_surface_cannot_fabricate_hash_when_raw_bytes_unavailable():
    capture = CanonicalRawResponseAccumulator(
        "sdk_native_structured",
        canonical_surface_available=False,
    )

    result = capture.finish_response()

    assert result.response_transport_mode == "sdk_native_structured"
    assert result.raw_provider_response is None
    assert result.raw_provider_response_hash is None


def test_rh9_completed_stream_hashes_exact_assembled_fragment_bytes():
    result = _capture_stream((b"[", b"1", b",", b"2", b"]"))

    assert result.raw_provider_response == b"[1,2]"
    assert result.raw_provider_response_hash == hashlib.sha256(b"[1,2]").hexdigest()


@pytest.mark.parametrize("delta", (-1, 0))
def test_raw_accumulator_accepts_inclusive_boundary(delta):
    limit = RESOURCE_LIMIT_VALUES["maximum_raw_response_bytes"]
    capture = CanonicalRawResponseAccumulator("non_streaming_http")
    capture.append(b"x" * (limit + delta))

    result = capture.finish_response()

    assert len(result.raw_provider_response) == limit + delta


def test_raw_accumulator_rejects_before_appending_limit_plus_one():
    limit = RESOURCE_LIMIT_VALUES["maximum_raw_response_bytes"]
    capture = CanonicalRawResponseAccumulator("non_streaming_http")
    capture.append(b"x" * limit)

    with pytest.raises(ResourceLimitExceededError) as caught:
        capture.append(b"x")

    assert caught.value.limit_name == "maximum_raw_response_bytes"
    assert capture.accumulated_bytes == 0
    with pytest.raises(TransportCaptureStateError, match="capture_failed_closed"):
        capture.finish_response()


@pytest.mark.parametrize("delta", (-1, 0))
def test_extracted_accumulator_accepts_inclusive_boundary(delta):
    limit = RESOURCE_LIMIT_VALUES["maximum_extracted_semantic_bytes"]
    capture = ExtractedSemanticAccumulator()
    capture.append(b"x" * (limit + delta))

    assert len(capture.finish()) == limit + delta


def test_extracted_accumulator_rejects_before_appending_limit_plus_one():
    limit = RESOURCE_LIMIT_VALUES["maximum_extracted_semantic_bytes"]
    capture = ExtractedSemanticAccumulator()
    capture.append(b"x" * limit)

    with pytest.raises(ResourceLimitExceededError) as caught:
        capture.append(b"x")

    assert caught.value.limit_name == "maximum_extracted_semantic_bytes"
    assert capture.accumulated_bytes == 0
    with pytest.raises(
        TransportCaptureStateError,
        match="semantic_capture_failed_closed",
    ):
        capture.finish()


def test_extracted_accumulator_preserves_exact_order_without_separators():
    capture = ExtractedSemanticAccumulator()
    capture.append(b'{"result":')
    capture.append(b"[")
    capture.append(b"]")
    capture.append(b"}")

    assert capture.finish() == b'{"result":[]}'


def test_streaming_applies_extracted_limit_before_appending_more_fragments():
    limit = RESOURCE_LIMIT_VALUES["maximum_extracted_semantic_bytes"]
    capture = CanonicalRawResponseAccumulator("streaming")
    capture.append(b"x" * limit)

    with pytest.raises(ResourceLimitExceededError) as caught:
        capture.append(b"x")

    assert caught.value.limit_name == "maximum_extracted_semantic_bytes"
    assert capture.accumulated_bytes == 0
    with pytest.raises(TransportCaptureStateError, match="capture_failed_closed"):
        capture.finish_stream(documented_terminal_complete=True)


def test_extracted_chunk_counter_validates_inputs_and_is_inclusive():
    limit = RESOURCE_LIMIT_VALUES["maximum_extracted_semantic_bytes"]
    assert account_extracted_semantic_chunk(limit - 1, b"x") == limit
    with pytest.raises(ResourceLimitExceededError):
        account_extracted_semantic_chunk(limit, b"x")
    with pytest.raises(TypeError):
        account_extracted_semantic_chunk(True, b"")
    with pytest.raises(ValueError):
        account_extracted_semantic_chunk(-1, b"")
    with pytest.raises(TypeError):
        account_extracted_semantic_chunk(0, bytearray())


def test_capture_lifecycle_and_type_contracts_fail_closed():
    with pytest.raises(ValueError, match="unsupported_response_transport_mode"):
        CanonicalRawResponseAccumulator("other")
    with pytest.raises(ValueError, match="unsupported_response_transport_mode"):
        CanonicalRawResponseAccumulator(type("Mode", (str,), {})("streaming"))
    with pytest.raises(TypeError):
        CanonicalRawResponseAccumulator(
            "non_streaming_http",
            canonical_surface_available=1,
        )
    with pytest.raises(TransportCaptureStateError):
        CanonicalRawResponseAccumulator(
            "streaming",
            canonical_surface_available=False,
        )

    unavailable = CanonicalRawResponseAccumulator(
        "non_streaming_http",
        canonical_surface_available=False,
    )
    with pytest.raises(TransportCaptureStateError):
        unavailable.append(b"x")

    response = CanonicalRawResponseAccumulator("non_streaming_http")
    with pytest.raises(TypeError):
        response.append(bytearray())
    with pytest.raises(TransportCaptureStateError):
        response.finish_stream(documented_terminal_complete=True)
    response.finish_response()
    with pytest.raises(TransportCaptureStateError):
        response.append(b"x")
    with pytest.raises(TransportCaptureStateError):
        response.finish_response()

    stream = CanonicalRawResponseAccumulator("streaming")
    with pytest.raises(TransportCaptureStateError):
        stream.finish_response()
    with pytest.raises(TypeError):
        stream.finish_stream(documented_terminal_complete=1)

    semantic = ExtractedSemanticAccumulator()
    semantic.finish()
    with pytest.raises(TransportCaptureStateError):
        semantic.append(b"x")
    with pytest.raises(TransportCaptureStateError):
        semantic.finish()


def test_raw_response_capture_direct_construction_enforces_all_invariants():
    digest = hashlib.sha256(b"{}").hexdigest()
    valid = RawResponseCapture(
        response_transport_mode="non_streaming_http",
        raw_provider_response=b"{}",
        raw_provider_response_hash=digest,
        canonical_raw_byte_availability=True,
    )
    assert valid.raw_provider_response_hash == digest

    with pytest.raises(ValueError, match="unsupported_response_transport_mode"):
        RawResponseCapture("other", b"{}", digest, True)
    with pytest.raises(TypeError, match="canonical_raw_byte_availability"):
        RawResponseCapture("non_streaming_http", b"{}", digest, 1)
    with pytest.raises(TypeError, match="available raw_provider_response"):
        RawResponseCapture("non_streaming_http", None, digest, True)
    with pytest.raises(ValueError, match="raw_provider_response_hash_mismatch"):
        RawResponseCapture("non_streaming_http", b"{}", "0" * 64, True)
    with pytest.raises(ValueError, match="unavailable_raw_surface"):
        RawResponseCapture("non_streaming_http", b"{}", digest, False)
    with pytest.raises(TransportExtractionError):
        RawResponseCapture("streaming", b"", EMPTY_SHA256, True)

    oversized_raw = b"x" * (
        RESOURCE_LIMIT_VALUES["maximum_raw_response_bytes"] + 1
    )
    with pytest.raises(ResourceLimitExceededError) as raw_failure:
        RawResponseCapture(
            "non_streaming_http",
            oversized_raw,
            hashlib.sha256(oversized_raw).hexdigest(),
            True,
        )
    assert raw_failure.value.limit_name == "maximum_raw_response_bytes"

    oversized_stream = b"x" * (
        RESOURCE_LIMIT_VALUES["maximum_extracted_semantic_bytes"] + 1
    )
    with pytest.raises(ResourceLimitExceededError) as stream_failure:
        RawResponseCapture(
            "streaming",
            oversized_stream,
            hashlib.sha256(oversized_stream).hexdigest(),
            True,
        )
    assert stream_failure.value.limit_name == "maximum_extracted_semantic_bytes"


def test_raw_response_capture_repr_never_contains_provider_bytes():
    sentinel = b"provider-secret-sentinel"
    capture = RawResponseCapture(
        response_transport_mode="non_streaming_http",
        raw_provider_response=sentinel,
        raw_provider_response_hash=hashlib.sha256(sentinel).hexdigest(),
        canonical_raw_byte_availability=True,
    )

    rendered = repr(capture)
    assert "provider-secret-sentinel" not in rendered
    assert hashlib.sha256(sentinel).hexdigest() not in rendered
