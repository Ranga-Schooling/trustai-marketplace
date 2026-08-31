"""Provider-neutral normalization primitives."""

from __future__ import annotations

import hashlib


def hash_raw_provider_response(raw_provider_response: bytes) -> str:
    """Return the SHA-256 identity of exact raw-provider-response bytes."""
    if not isinstance(raw_provider_response, bytes):
        raise TypeError("raw_provider_response must be bytes")
    return hashlib.sha256(raw_provider_response).hexdigest()
