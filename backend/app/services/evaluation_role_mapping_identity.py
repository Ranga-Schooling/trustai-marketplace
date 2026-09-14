"""Provider-neutral semantic identity for frozen request-role mappings.

The common contract freezes how one concrete mapping is identified and
hashed, but concrete provider mappings remain a separate, pending artifact.
This module therefore verifies identity only.  It does not validate provider
capabilities, select a mapping, build a request, or authorize execution.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from app.services.normalization_parser import (
    NumericDomainError,
    StrictJsonPayloadError,
    normalize_semantic_json,
)


_IDENTITY_DOMAIN = "trustai.provider_role_mapping.v1"
_ENVELOPE_KEYS = frozenset(
    {
        "identity_domain",
        "provider_role_mapping_id",
        "provider_role_mapping_version",
        "content",
    }
)
_LOWER_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class ProviderRoleMappingIdentityError(ValueError):
    """A concrete role-mapping identity envelope is malformed or stale."""


@dataclass(frozen=True)
class ProviderRoleMappingIdentity:
    """Immutable independently recomputed mapping identity."""

    identity_domain: str
    mapping_id: str
    mapping_version: str
    semantic_hash: str
    independently_authorizes_execution: bool = False


def _parse_and_canonicalize(envelope_json: bytes):
    if type(envelope_json) is not bytes:
        raise ProviderRoleMappingIdentityError(
            "provider_role_mapping_envelope_bytes"
        )
    try:
        return normalize_semantic_json(envelope_json)
    except (
        StrictJsonPayloadError,
        NumericDomainError,
        TypeError,
        ValueError,
        RecursionError,
    ) as exc:
        raise ProviderRoleMappingIdentityError(
            "provider_role_mapping_strict_json"
        ) from exc


def compute_provider_role_mapping_identity(
    envelope_json: bytes,
) -> ProviderRoleMappingIdentity:
    """Hash one exact four-key envelope under the frozen canonical parser."""
    normalized = _parse_and_canonicalize(envelope_json)
    envelope = normalized.admitted.value
    if not isinstance(envelope, dict):
        raise ProviderRoleMappingIdentityError(
            "provider_role_mapping_envelope"
        )
    if set(envelope) != _ENVELOPE_KEYS:
        raise ProviderRoleMappingIdentityError(
            "provider_role_mapping_envelope_keys"
        )

    identity_domain = envelope["identity_domain"]
    mapping_id = envelope["provider_role_mapping_id"]
    mapping_version = envelope["provider_role_mapping_version"]
    content = envelope["content"]
    if type(identity_domain) is not str or identity_domain != _IDENTITY_DOMAIN:
        raise ProviderRoleMappingIdentityError(
            "provider_role_mapping_identity_domain"
        )
    if type(mapping_id) is not str:
        raise ProviderRoleMappingIdentityError("provider_role_mapping_id")
    if type(mapping_version) is not str:
        raise ProviderRoleMappingIdentityError("provider_role_mapping_version")
    if not isinstance(content, dict):
        raise ProviderRoleMappingIdentityError("provider_role_mapping_content")

    return ProviderRoleMappingIdentity(
        identity_domain=_IDENTITY_DOMAIN,
        mapping_id=mapping_id,
        mapping_version=mapping_version,
        semantic_hash=normalized.strict_parsed_semantic_payload_hash,
    )


def verify_provider_role_mapping_hash(
    envelope_json: bytes,
    stored_hash: str,
) -> ProviderRoleMappingIdentity:
    """Require a stored lowercase SHA-256 to match independent recomputation."""
    if type(stored_hash) is not str or _LOWER_SHA256.fullmatch(stored_hash) is None:
        raise ProviderRoleMappingIdentityError(
            "provider_role_mapping_hash_format"
        )
    identity = compute_provider_role_mapping_identity(envelope_json)
    if identity.semantic_hash != stored_hash:
        raise ProviderRoleMappingIdentityError(
            "provider_role_mapping_hash_mismatch"
        )
    return identity
