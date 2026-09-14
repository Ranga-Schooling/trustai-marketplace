"""Provider-neutral bounded capture of frozen transport byte surfaces."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from app.services.evaluation_resource_limits import (
    ResourceLimitExceededError,
    account_extracted_semantic_chunk,
    account_raw_response_chunk,
)


RESPONSE_TRANSPORT_MODES = (
    "non_streaming_http",
    "streaming",
    "sdk_native_structured",
)


class TransportCaptureStateError(ValueError):
    """The provider-neutral capture lifecycle was used inconsistently."""


class TransportExtractionError(ValueError):
    """A frozen transport-extraction rule rejected the captured surface."""

    category = "failed_transport_extraction"


@dataclass(frozen=True, slots=True)
class RawResponseCapture:
    """Validated kernel output, not a complete provider-adapter result.

    Provider adapters must separately supply the frozen unavailable reason,
    terminal-state evidence, framing identity, and all safe transport metadata.
    """

    response_transport_mode: str
    raw_provider_response: bytes | None = field(repr=False)
    raw_provider_response_hash: str | None = field(repr=False)
    canonical_raw_byte_availability: bool

    def __post_init__(self) -> None:
        if (
            type(self.response_transport_mode) is not str
            or self.response_transport_mode not in RESPONSE_TRANSPORT_MODES
        ):
            raise ValueError("unsupported_response_transport_mode")
        if type(self.canonical_raw_byte_availability) is not bool:
            raise TypeError("canonical_raw_byte_availability must be a boolean")
        if self.canonical_raw_byte_availability:
            if type(self.raw_provider_response) is not bytes:
                raise TypeError("available raw_provider_response must be bytes")
            account_raw_response_chunk(0, self.raw_provider_response)
            if self.response_transport_mode == "streaming":
                account_extracted_semantic_chunk(0, self.raw_provider_response)
                if not self.raw_provider_response:
                    raise TransportExtractionError(
                        "completed_stream_has_no_semantic_payload"
                    )
            expected_hash = hashlib.sha256(self.raw_provider_response).hexdigest()
            if (
                type(self.raw_provider_response_hash) is not str
                or self.raw_provider_response_hash != expected_hash
            ):
                raise ValueError("raw_provider_response_hash_mismatch")
        elif (
            self.raw_provider_response is not None
            or self.raw_provider_response_hash is not None
        ):
            raise ValueError("unavailable_raw_surface_must_not_have_identity")


class CanonicalRawResponseAccumulator:
    """Bound canonical raw bytes before storage, hashing, or semantic work.

    Callers own HTTP decoding, provider framing, designated-fragment selection,
    and terminal-state interpretation. Streaming callers may append only exact
    provider-designated semantic fragment bytes in documented event order.
    """

    def __init__(
        self,
        response_transport_mode: str,
        *,
        canonical_surface_available: bool = True,
    ) -> None:
        if (
            type(response_transport_mode) is not str
            or response_transport_mode not in RESPONSE_TRANSPORT_MODES
        ):
            raise ValueError("unsupported_response_transport_mode")
        if not isinstance(canonical_surface_available, bool):
            raise TypeError("canonical_surface_available must be a boolean")
        if response_transport_mode == "streaming" and not canonical_surface_available:
            raise TransportCaptureStateError(
                "streaming_unavailability_requires_incomplete_stream_finalization"
            )
        self._response_transport_mode = response_transport_mode
        self._canonical_surface_available = canonical_surface_available
        self._buffer = bytearray()
        self._finished = False
        self._failed = False

    @property
    def accumulated_bytes(self) -> int:
        """Return the bounded byte count without exposing a partial prefix."""
        return len(self._buffer)

    def append(self, chunk: bytes) -> None:
        """Account one exact byte fragment before appending it to storage."""
        self._require_open()
        if not self._canonical_surface_available:
            raise TransportCaptureStateError("canonical_raw_surface_unavailable")
        try:
            new_size = account_raw_response_chunk(len(self._buffer), chunk)
            if self._response_transport_mode == "streaming":
                account_extracted_semantic_chunk(len(self._buffer), chunk)
        except ResourceLimitExceededError:
            self._fail_closed()
            raise
        self._buffer.extend(chunk)
        if len(self._buffer) != new_size:
            raise AssertionError("raw_response_byte_accounting_mismatch")

    def finish_response(self) -> RawResponseCapture:
        """Finalize a non-streaming or pre-SDK canonical byte surface."""
        self._require_open()
        if self._response_transport_mode == "streaming":
            raise TransportCaptureStateError("stream_requires_terminal_state")
        self._finished = True
        if not self._canonical_surface_available:
            return self._unavailable_capture()
        return self._completed_capture()

    def finish_stream(
        self,
        *,
        documented_terminal_complete: bool,
    ) -> RawResponseCapture:
        """Publish only after external frozen adapter evidence proves completion.

        This kernel does not establish or validate provider terminal semantics;
        the boolean is not topology evidence and cannot make an adapter eligible.
        """
        self._require_open()
        if self._response_transport_mode != "streaming":
            raise TransportCaptureStateError("non_stream_does_not_have_terminal_state")
        if type(documented_terminal_complete) is not bool:
            raise TypeError("documented_terminal_complete must be a boolean")
        self._finished = True
        if not documented_terminal_complete:
            self._buffer.clear()
            return self._unavailable_capture()
        if not self._buffer:
            raise TransportExtractionError("completed_stream_has_no_semantic_payload")
        return self._completed_capture()

    def _require_open(self) -> None:
        if self._failed:
            raise TransportCaptureStateError("capture_failed_closed")
        if self._finished:
            raise TransportCaptureStateError("capture_already_finished")

    def _fail_closed(self) -> None:
        self._failed = True
        self._buffer.clear()

    def _completed_capture(self) -> RawResponseCapture:
        raw_bytes = bytes(self._buffer)
        result = RawResponseCapture(
            response_transport_mode=self._response_transport_mode,
            raw_provider_response=raw_bytes,
            raw_provider_response_hash=hashlib.sha256(raw_bytes).hexdigest(),
            canonical_raw_byte_availability=True,
        )
        self._buffer.clear()
        return result

    def _unavailable_capture(self) -> RawResponseCapture:
        return RawResponseCapture(
            response_transport_mode=self._response_transport_mode,
            raw_provider_response=None,
            raw_provider_response_hash=None,
            canonical_raw_byte_availability=False,
        )


class ExtractedSemanticAccumulator:
    """Bound designated semantic bytes before UTF-8 or JSON processing."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._finished = False
        self._failed = False

    @property
    def accumulated_bytes(self) -> int:
        """Return the bounded byte count without exposing partial bytes."""
        return len(self._buffer)

    def append(self, fragment: bytes) -> None:
        """Account an exact designated fragment before appending it."""
        self._require_open()
        try:
            new_size = account_extracted_semantic_chunk(len(self._buffer), fragment)
        except ResourceLimitExceededError:
            self._failed = True
            self._buffer.clear()
            raise
        self._buffer.extend(fragment)
        if len(self._buffer) != new_size:
            raise AssertionError("semantic_byte_accounting_mismatch")

    def finish(self) -> bytes:
        """Return exact bytes without parsing, decoding, repair, or selection."""
        self._require_open()
        self._finished = True
        result = bytes(self._buffer)
        self._buffer.clear()
        return result

    def _require_open(self) -> None:
        if self._failed:
            raise TransportCaptureStateError("semantic_capture_failed_closed")
        if self._finished:
            raise TransportCaptureStateError("semantic_capture_already_finished")
