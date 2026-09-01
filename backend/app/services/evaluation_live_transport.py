"""Concrete, inert-until-invoked HTTP transports for the frozen pilot.

The module owns only the final credential/header and HTTPS boundary.  It has
no import-time environment read, client construction, DNS, socket, telemetry,
retry, provider discovery, persistence, or execution authority.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import json
import os
from time import monotonic
from typing import Any, Protocol

from app.services.evaluation_pilot_runner import (
    CREDENTIAL_VARIABLE_BY_PROVIDER,
    NativeProviderRequest,
    PilotRunnerError,
    TransportResponse,
    _ResolvedCredential,
    _TRANSPORT_SECRET_TOKEN,
)
from app.services.evaluation_resource_limits import ResourceLimitExceededError
from app.services.evaluation_retry_policy import AttemptDeadline
from app.services.evaluation_transport_capture import CanonicalRawResponseAccumulator


_ENDPOINT_BY_PROVIDER = {
    "OpenAI": "https://api.openai.com/v1/responses",
    "Google Gemini": "https://generativelanguage.googleapis.com/v1beta/interactions",
    "Groq": "https://api.groq.com/openai/v1/chat/completions",
}
_API_FAMILY_BY_PROVIDER = {
    "OpenAI": "Responses API",
    "Google Gemini": "Gemini Interactions API v1beta with Api-Revision 2026-05-20",
    "Groq": None,
}
_REDACTED_HEADER_NAMES = frozenset({"authorization", "x-goog-api-key"})


class LiveTransportError(ValueError):
    """A safe live-boundary invariant failed before provider interpretation."""


class HttpConnectionFailure(LiveTransportError):
    """The HTTP boundary failed before a response body existed."""


class HttpTimeoutFailure(LiveTransportError):
    """The HTTP boundary reached the frozen per-attempt timeout."""


def _fail(code: str) -> LiveTransportError:
    return LiveTransportError(code)


@dataclass(frozen=True, slots=True)
class HttpRequest:
    method: str
    url: str
    headers: tuple[tuple[str, str], ...] = field(repr=False)
    body: bytes = field(repr=False)
    timeout_seconds: int

    def __post_init__(self) -> None:
        if (
            self.method != "POST"
            or self.url not in _ENDPOINT_BY_PROVIDER.values()
            or type(self.body) is not bytes
            or self.timeout_seconds != 120
            or type(self.headers) is not tuple
            or any(
                type(item) is not tuple
                or len(item) != 2
                or any(type(value) is not str or not value for value in item)
                for item in self.headers
            )
        ):
            raise _fail("http_request")

    def safe_projection(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "url": self.url,
            "headers": {
                name: "<redacted>" if name.lower() in _REDACTED_HEADER_NAMES else value
                for name, value in self.headers
            },
            "body_bytes": len(self.body),
            "timeout_seconds": self.timeout_seconds,
        }

    def __repr__(self) -> str:
        return f"HttpRequest({self.safe_projection()!r})"


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    body_chunks: tuple[bytes, ...] = field(repr=False)
    headers: Mapping[str, str] = field(repr=False)
    elapsed_seconds: float

    def __post_init__(self) -> None:
        if (
            type(self.status_code) is not int
            or not 100 <= self.status_code <= 599
            or type(self.body_chunks) is not tuple
            or any(type(chunk) is not bytes for chunk in self.body_chunks)
            or type(self.elapsed_seconds) not in (int, float)
            or self.elapsed_seconds < 0
        ):
            raise _fail("http_response")


class HttpSender(Protocol):
    """Exactly one physical HTTP invocation; retries belong to the runner."""

    def send(self, request: HttpRequest) -> HttpResponse: ...


class HttpxSender:
    """One synchronous httpx request with no application or transport retries."""

    __slots__ = ()

    def validate_runtime(self) -> None:
        """Fail offline when the configured HTTP client is unavailable."""
        _load_httpx()

    def send(self, request: HttpRequest) -> HttpResponse:
        if not isinstance(request, HttpRequest):
            raise _fail("http_request")
        # Client creation occurs only at the authorized call boundary; the
        # dependency itself may already have been checked by offline preflight.
        httpx = _load_httpx()

        accumulator = CanonicalRawResponseAccumulator("non_streaming_http")
        started_at = monotonic()
        try:
            with httpx.Client(
                timeout=httpx.Timeout(request.timeout_seconds),
                follow_redirects=False,
            ) as client:
                with client.stream(
                    request.method,
                    request.url,
                    headers=dict(request.headers),
                    content=request.body,
                ) as response:
                    for chunk in response.iter_bytes():
                        accumulator.append(chunk)
                    capture = accumulator.finish_response()
                    body = capture.raw_provider_response
                    if body is None:
                        raise _fail("http_body")
                    status_code = response.status_code
                    content_type = response.headers.get("content-type", "")
            elapsed_seconds = monotonic() - started_at
            if elapsed_seconds < 0:
                raise _fail("http_elapsed")
            return HttpResponse(
                status_code,
                (body,),
                {"content-type": content_type},
                elapsed_seconds,
            )
        except httpx.TimeoutException as exc:
            raise HttpTimeoutFailure("provider_attempt_timeout") from exc
        except httpx.TransportError as exc:
            raise HttpConnectionFailure("provider_connection_error") from exc

    def __repr__(self) -> str:
        return "HttpxSender(retries=0, state=inert_until_send)"


class LazyEnvironmentCredentialResolver:
    """Read one named process variable only when ``resolve`` is invoked."""

    __slots__ = ("_getter", "_requested")

    def __init__(self, getter: Callable[[str], str | None] | None = None) -> None:
        self._getter = getter if getter is not None else os.environ.get
        self._requested: list[str] = []

    def resolve(self, reference):
        expected = CREDENTIAL_VARIABLE_BY_PROVIDER.get(getattr(reference, "provider", None))
        if expected is None or reference.environment_variable_name != expected:
            raise PilotRunnerError("credential_reference")
        value = self._getter(reference.environment_variable_name)
        self._requested.append(reference.environment_variable_name)
        if type(value) is not str or not value:
            raise PilotRunnerError("credential_unavailable")
        return _ResolvedCredential(reference, value, _token=_TRANSPORT_SECRET_TOKEN)

    @property
    def resolution_count(self) -> int:
        return len(self._requested)

    @property
    def requested_environment_variable_names(self) -> tuple[str, ...]:
        return tuple(self._requested)

    def __repr__(self) -> str:
        return (
            "LazyEnvironmentCredentialResolver("
            f"requested_environment_variable_names={tuple(self._requested)!r}, "
            "values=<redacted>)"
        )


def credential_presence_lines(
    getter: Callable[[str], str | None] | None = None,
) -> tuple[str, ...]:
    """Return only variable names plus PRESENT/MISSING; never value metadata."""
    read = getter if getter is not None else os.environ.get
    lines = []
    for name in CREDENTIAL_VARIABLE_BY_PROVIDER.values():
        value = read(name)
        lines.append(f"{name}={'PRESENT' if type(value) is str and bool(value) else 'MISSING'}")
        del value
    return tuple(lines)


class ConcreteLivePilotTransport:
    """Dispatch the frozen native request through one injected HTTP sender."""

    __slots__ = ("_sender", "_invocation_count")

    def __init__(self, sender: HttpSender) -> None:
        if not hasattr(sender, "send"):
            raise _fail("http_sender")
        self._sender = sender
        self._invocation_count = 0

    @property
    def invocation_count(self) -> int:
        return self._invocation_count

    def validate_runtime(self) -> None:
        """Validate local sender dependencies without credentials or I/O."""
        validator = getattr(self._sender, "validate_runtime", None)
        if validator is not None:
            validator()

    def invoke(
        self,
        request: NativeProviderRequest,
        credential: _ResolvedCredential,
        deadline: AttemptDeadline,
    ) -> TransportResponse:
        if not isinstance(request, NativeProviderRequest):
            raise _fail("transport_request")
        if not isinstance(deadline, AttemptDeadline) or deadline.timeout_seconds != 120:
            raise _fail("transport_deadline")
        provider = request.call.provider
        endpoint = _ENDPOINT_BY_PROVIDER.get(provider)
        if endpoint is None or credential.provider != provider:
            raise _fail("transport_provider")
        _validate_native_payload(request)
        secret = credential._transport_value(_TRANSPORT_SECRET_TOKEN)
        headers = [("content-type", "application/json"), ("accept", "application/json")]
        if provider == "Google Gemini":
            headers.extend(
                (("x-goog-api-key", secret), ("api-revision", "2026-05-20"))
            )
        else:
            headers.append(("authorization", f"Bearer {secret}"))
        outgoing = HttpRequest(
            method="POST",
            url=endpoint,
            headers=tuple(headers),
            body=request.payload_json,
            timeout_seconds=deadline.timeout_seconds,
        )
        self._invocation_count += 1
        try:
            response = self._sender.send(outgoing)
        except HttpTimeoutFailure:
            return TransportResponse(0, b"", 120.0, "timeout")
        except HttpConnectionFailure:
            return TransportResponse(0, b"", 0.0, "connection")
        except Exception:
            # The physical invocation counter was already incremented.  An
            # unexpected client/sender failure therefore cannot be treated as
            # a preflight error or expose diagnostic prose; the runner will
            # preserve it as an invoked attempt with unresolved exact cost.
            return TransportResponse(0, b"", 0.0, "connection")
        accumulator = CanonicalRawResponseAccumulator("non_streaming_http")
        try:
            for chunk in response.body_chunks:
                accumulator.append(chunk)
            capture = accumulator.finish_response()
        except ResourceLimitExceededError:
            return TransportResponse(
                response.status_code,
                b"",
                response.elapsed_seconds,
                "malformed",
            )
        body = capture.raw_provider_response
        if body is None:
            raise _fail("http_body")
        content_type = _header(response.headers, "content-type")
        signal = _http_failure_signal(response.status_code)
        if signal is None and not _is_json_content_type(content_type):
            signal = "malformed"
        return TransportResponse(
            response.status_code,
            body,
            response.elapsed_seconds,
            signal,
            (("content-type", content_type),),
        )

    def __repr__(self) -> str:
        return (
            "ConcreteLivePilotTransport("
            f"invocation_count={self._invocation_count}, sender=<redacted>)"
        )


def _validate_native_payload(request: NativeProviderRequest) -> None:
    try:
        payload = json.loads(request.payload_json.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _fail("request_payload") from exc
    if payload.get("model") != request.call.model or payload.get("stream") is not False:
        raise _fail("request_payload")
    provider = request.call.provider
    api_family = request.call.api_family
    expected_family = _API_FAMILY_BY_PROVIDER[provider]
    if expected_family is not None and api_family != expected_family:
        raise _fail("api_family")
    if provider == "OpenAI":
        if payload.get("store") is not False or "input" not in payload:
            raise _fail("request_payload")
    elif provider == "Google Gemini":
        response_format = payload.get("response_format")
        if (
            response_format is None
            or response_format.get("type") != "text"
            or response_format.get("mime_type") != "application/json"
            or type(response_format.get("schema")) is not dict
            or "json_schema" in response_format
            or payload.get("store") is not False
        ):
            raise _fail("request_payload")
    elif provider == "Groq":
        if "messages" not in payload or "store" in payload:
            raise _fail("request_payload")


def _load_httpx():
    try:
        import httpx
    except ImportError as exc:
        raise _fail("http_client_unavailable") from exc
    required = ("Client", "Timeout", "TimeoutException", "TransportError")
    if any(not hasattr(httpx, name) for name in required):
        raise _fail("http_client_unavailable")
    return httpx


def _header(headers: Mapping[str, str], name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name:
            return value
    return ""


def _is_json_content_type(value: str) -> bool:
    media_type = value.split(";", 1)[0].strip().lower()
    return media_type == "application/json" or media_type.endswith("+json")


def _http_failure_signal(status: int) -> str | None:
    if 200 <= status <= 299:
        return None
    if status == 429:
        return "rate_limit"
    if status in {500, 502, 503, 504}:
        return "service_unavailable"
    return "http_failure"
