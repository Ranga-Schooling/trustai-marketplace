"""Deterministic URL-security validation for the frozen evaluation policy."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any


_POLICY_ID = "url_security_policy_v1"
_POLICY_VERSION = "v1"
_POLICY_HASH = "fcc37b299f84cccb7522c2db150022e3e92f04430c50e01b94bb7f7fa6e5b44e"

_URL_ROLES = {"requested_url", "intermediate_redirect_url", "final_url"}
_AUTH_CONTEXTS = {
    "public_unauthenticated",
    "authenticated",
    "session_bound",
    "credential_bearing",
    "signed_private_access",
    "unknown",
}
_SENSITIVE_AUTH_CONTEXTS = {
    "authenticated",
    "session_bound",
    "credential_bearing",
    "signed_private_access",
}
_SIGNED_NAMES = {
    "x-amz-credential",
    "x-amz-signature",
    "x-amz-security-token",
    "x-goog-credential",
    "x-goog-signature",
    "googleaccessid",
    "signature",
    "sig",
}
_SENSITIVE_NAMES = {
    "access_token",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "session",
    "sessionid",
    "code",
    "credential",
    "password",
    "secret",
    "jwt",
}
_REASON_PRECEDENCE = (
    "userinfo_present",
    "signed_url_detected",
    "authenticated_context",
    "sensitive_redirect_context",
    "recognized_sensitive_query_material",
)
_ORIGIN_KEYS = {"scheme", "host_kind", "host", "effective_port"}
_MATCHED_RULE_KEYS = {
    "status",
    "rule_id",
    "rule_version",
    "origin_identity",
    "path_match",
    "query_match",
    "fragment_match",
    "public_shareability_established",
    "exact_url_disclosure_grants_access",
    "rule_hash",
}
_REDIRECT_KEYS = {
    "capture_status",
    "current_position",
    "requested_position",
    "final_position",
    "members",
}
_REDIRECT_MEMBER_KEYS = {
    "position",
    "url_role",
    "exact_url",
    "retrieval_auth_context",
    "origin_rule",
    "restricted_trace_reference",
}
_HEX_RE = re.compile(r"[0-9A-Fa-f]+")
_SCHEME_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*")
_LOWER_HEX_64_RE = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class _ParsedUrl:
    valid: bool
    reasons: frozenset[str]
    origin_identity: dict[str, Any] | None
    path: str
    query_present: bool
    query: str
    fragment_present: bool
    fragment: str

    @property
    def loop_identity(self) -> dict[str, Any] | None:
        if not self.valid or self.origin_identity is None:
            return None
        return {
            "origin_identity": self.origin_identity,
            "path": self.path,
            "query_present": self.query_present,
            "query": self.query,
            "fragment_present": self.fragment_present,
            "fragment": self.fragment,
        }


@dataclass(frozen=True)
class _DirectResult:
    reasons: frozenset[str]
    indeterminate: bool
    loop_identity: dict[str, Any] | None

    @property
    def sensitive(self) -> bool:
        return bool(self.reasons)

    @property
    def public_safe(self) -> bool:
        return not self.reasons and not self.indeterminate


def _ascii_lower(value: str) -> str:
    return "".join(chr(ord(char) + 32) if "A" <= char <= "Z" else char for char in value)


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _exact_json_equal(left: Any, right: Any) -> bool:
    pending = [(left, right)]
    while pending:
        left_item, right_item = pending.pop()
        if type(left_item) is not type(right_item):
            return False
        if isinstance(left_item, dict):
            if left_item.keys() != right_item.keys():
                return False
            pending.extend((left_item[key], right_item[key]) for key in left_item)
        elif isinstance(left_item, list):
            if len(left_item) != len(right_item):
                return False
            pending.extend(zip(left_item, right_item, strict=True))
        elif left_item != right_item:
            return False
    return True


def _decode_once(raw: str) -> tuple[str, bool]:
    decoded: list[str] = []
    valid = True
    index = 0
    while index < len(raw):
        char = raw[index]
        if char != "%":
            decoded.append(char)
            index += 1
            continue
        if index + 2 >= len(raw) or not _HEX_RE.fullmatch(raw[index + 1 : index + 3]):
            decoded.append("%")
            valid = False
            index += 1
            continue
        octet = int(raw[index + 1 : index + 3], 16)
        mapped = chr(octet)
        decoded.append(mapped)
        if octet > 0x7F or octet <= 0x20 or octet == 0x7F or mapped == "\\":
            valid = False
        index += 3

    value = "".join(decoded)
    for offset in range(max(0, len(value) - 2)):
        if value[offset] == "%" and _HEX_RE.fullmatch(value[offset + 1 : offset + 3]):
            valid = False
            break
    return value, valid


def _contains_encoded_name_delimiter(raw: str) -> bool:
    for index in range(max(0, len(raw) - 2)):
        if raw[index] != "%" or _HEX_RE.fullmatch(raw[index + 1 : index + 3]) is None:
            continue
        if chr(int(raw[index + 1 : index + 3], 16)) in {"&", "=", ";"}:
            return True
    return False


def _inspect_fields(raw: str, present: bool) -> tuple[set[str], bool]:
    if not present:
        return set(), True

    reasons: set[str] = set()
    valid = True
    for raw_field in raw.split("&"):
        if "=" in raw_field:
            raw_name, raw_value = raw_field.split("=", 1)
        else:
            raw_name, raw_value = raw_field, None

        raw_folded = _ascii_lower(raw_name)
        if raw_folded in _SIGNED_NAMES:
            reasons.add("signed_url_detected")
        if raw_folded in _SENSITIVE_NAMES:
            reasons.add("recognized_sensitive_query_material")

        decoded_name, name_valid = _decode_once(raw_name)
        decoded_folded = _ascii_lower(decoded_name)
        if decoded_folded in _SIGNED_NAMES:
            reasons.add("signed_url_detected")
        if decoded_folded in _SENSITIVE_NAMES:
            reasons.add("recognized_sensitive_query_material")
        if _contains_encoded_name_delimiter(raw_name):
            name_valid = False
        valid = valid and name_valid

        if raw_value is not None:
            _, value_valid = _decode_once(raw_value)
            valid = valid and value_valid

    return reasons, valid


def _is_grant(segment: str) -> bool:
    return bool(segment) and "/" not in segment and "." not in segment


def _has_sensitive_path_sequence(segments: list[str]) -> bool:
    patterns = (
        ("password-reset",),
        ("reset-password",),
        ("email-verification",),
        ("verify-email",),
        ("private", "share"),
    )
    for prefix in patterns:
        width = len(prefix) + 1
        for start in range(len(segments) - width + 1):
            candidate = segments[start : start + width]
            if tuple(candidate[:-1]) == prefix and _is_grant(candidate[-1]):
                return True
    return False


def _inspect_path(raw: str) -> tuple[set[str], bool]:
    decoded_segments: list[str] = []
    valid = True
    for raw_segment in raw.split("/"):
        decoded, segment_valid = _decode_once(raw_segment)
        if "/" in decoded or decoded in {".", ".."}:
            segment_valid = False
        decoded_segments.append(_ascii_lower(decoded))
        valid = valid and segment_valid

    reasons: set[str] = set()
    if _has_sensitive_path_sequence(decoded_segments):
        reasons.add("recognized_sensitive_query_material")
    return reasons, valid


def _parse_ipv4(raw: str) -> str | None:
    parts = raw.split(".")
    if len(parts) != 4:
        return None
    values: list[int] = []
    for part in parts:
        if not part or not part.isascii() or not part.isdigit():
            return None
        if len(part) > 1 and part[0] == "0":
            return None
        if len(part) > 3:
            return None
        number = int(part)
        if number > 255:
            return None
        values.append(number)
    return ".".join(str(value) for value in values)


def _is_forbidden_alternate_ipv4(raw: str) -> bool:
    if raw and raw.isascii() and raw.isdigit():
        return True
    if len(raw) > 2 and raw[:2].lower() == "0x" and _HEX_RE.fullmatch(raw[2:]):
        return True
    parts = raw.split(".")
    if len(parts) < 2:
        return False
    return all(
        bool(part)
        and (
            (part.isascii() and part.isdigit())
            or (
                len(part) > 2
                and part[:2].lower() == "0x"
                and _HEX_RE.fullmatch(part[2:]) is not None
            )
        )
        for part in parts
    )


def _parse_dns(raw: str) -> str | None:
    if not raw or len(raw) > 253 or not raw.isascii() or raw.endswith("."):
        return None
    labels = raw.split(".")
    for label in labels:
        if not 1 <= len(label) <= 63 or label[0] == "-" or label[-1] == "-":
            return None
        if any(not (char.isascii() and (char.isalnum() or char == "-")) for char in label):
            return None
    return _ascii_lower(raw)


def _parse_ipv6(raw: str) -> str | None:
    if not raw or "." in raw or "%" in raw or any(
        char not in "0123456789abcdefABCDEF:" for char in raw
    ):
        return None
    if raw.count("::") > 1:
        return None

    if "::" in raw:
        left_raw, right_raw = raw.split("::", 1)
        left = left_raw.split(":") if left_raw else []
        right = right_raw.split(":") if right_raw else []
        if any(not part for part in left + right):
            return None
        missing = 8 - len(left) - len(right)
        if missing < 1:
            return None
        parts = left + (["0"] * missing) + right
    else:
        parts = raw.split(":")
        if len(parts) != 8 or any(not part for part in parts):
            return None

    if len(parts) != 8 or any(
        len(part) > 4 or _HEX_RE.fullmatch(part) is None for part in parts
    ):
        return None
    values = [int(part, 16) for part in parts]

    best_start = -1
    best_length = 0
    start = 0
    while start < len(values):
        if values[start] != 0:
            start += 1
            continue
        end = start
        while end < len(values) and values[end] == 0:
            end += 1
        length = end - start
        if length >= 2 and length > best_length:
            best_start = start
            best_length = length
        start = end

    groups = [format(value, "x") for value in values]
    if best_start < 0:
        return ":".join(groups)
    left = ":".join(groups[:best_start])
    right = ":".join(groups[best_start + best_length :])
    if not left and not right:
        return "::"
    if not left:
        return f"::{right}"
    if not right:
        return f"{left}::"
    return f"{left}::{right}"


def _parse_host(raw: str) -> tuple[str, str] | None:
    if not raw or not raw.isascii() or "%" in raw or raw.endswith("."):
        return None
    canonical_ipv4 = _parse_ipv4(raw)
    if canonical_ipv4 is not None:
        return "ipv4", canonical_ipv4
    if _is_forbidden_alternate_ipv4(raw):
        return None
    canonical_dns = _parse_dns(raw)
    if canonical_dns is not None:
        return "dns", canonical_dns
    return None


def _parse_authority(raw: str) -> tuple[tuple[str, str] | None, str | None, bool]:
    if raw.startswith("["):
        closing = raw.find("]")
        if closing < 0:
            return None, None, False
        host = _parse_ipv6(raw[1:closing])
        remainder = raw[closing + 1 :]
        if host is None or (remainder and not remainder.startswith(":")):
            return None, None, False
        port = remainder[1:] if remainder else None
        return ("ipv6", host), port, True

    if "[" in raw or "]" in raw or raw.count(":") > 1:
        return None, None, False
    if ":" in raw:
        host_raw, port = raw.split(":", 1)
    else:
        host_raw, port = raw, None
    host = _parse_host(host_raw)
    return host, port, host is not None


def _parse_port(raw: str | None, scheme: str) -> tuple[int | None, bool]:
    if raw is None:
        return (80 if scheme == "http" else 443), True
    if not raw or not raw.isascii() or not raw.isdigit():
        return None, False
    if len(raw) > 1 and raw[0] == "0":
        return None, False
    if len(raw) > 5:
        return None, False
    value = int(raw)
    if value > 65535:
        return None, False
    return value, True


def _parse_url(exact_url: Any) -> _ParsedUrl:
    if not isinstance(exact_url, str) or not exact_url:
        return _ParsedUrl(False, frozenset(), None, "", False, "", False, "")

    before_fragment, fragment_marker, fragment = exact_url.partition("#")
    fragment_present = bool(fragment_marker)
    before_query, query_marker, query = before_fragment.partition("?")
    query_present = bool(query_marker)
    reasons: set[str] = set()
    valid = not any(
        ord(char) > 0x7F or ord(char) <= 0x20 or ord(char) == 0x7F or char == "\\"
        for char in exact_url
    )

    query_reasons, query_valid = _inspect_fields(query, query_present)
    fragment_reasons, fragment_valid = _inspect_fields(fragment, fragment_present)
    reasons.update(query_reasons)
    reasons.update(fragment_reasons)
    valid = valid and query_valid and fragment_valid

    path = ""
    origin_identity: dict[str, Any] | None = None
    colon = before_query.find(":")
    scheme_raw = before_query[:colon] if colon >= 0 else ""
    remainder = before_query[colon + 1 :] if colon >= 0 else ""
    has_authority_candidate = colon >= 0 and remainder.startswith("//")
    authority = ""
    if has_authority_candidate:
        authority_and_path = remainder[2:]
        slash = authority_and_path.find("/")
        if slash < 0:
            authority = authority_and_path
        else:
            authority = authority_and_path[:slash]
            path = authority_and_path[slash:]
        path_reasons, path_valid = _inspect_path(path)
        reasons.update(path_reasons)
        valid = valid and path_valid
        if "@" in authority:
            reasons.add("userinfo_present")

    scheme_valid = (
        has_authority_candidate
        and _SCHEME_RE.fullmatch(scheme_raw) is not None
        and _ascii_lower(scheme_raw) in {"http", "https"}
    )
    valid = valid and scheme_valid
    scheme = _ascii_lower(scheme_raw) if scheme_valid else ""

    if has_authority_candidate:
        host_port = authority.rsplit("@", 1)[-1]
        host, raw_port, authority_valid = _parse_authority(host_port)
        effective_port, port_valid = _parse_port(raw_port, scheme) if scheme_valid else (None, False)
        valid = valid and authority_valid and port_valid
        if valid and host is not None and effective_port is not None:
            host_kind, canonical_host = host
            origin_identity = {
                "scheme": scheme,
                "host_kind": host_kind,
                "host": canonical_host,
                "effective_port": effective_port,
            }
    else:
        valid = False

    return _ParsedUrl(
        valid,
        frozenset(reasons),
        origin_identity,
        path,
        query_present,
        query,
        fragment_present,
        fragment,
    )


def _valid_origin_identity(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == _ORIGIN_KEYS
        and isinstance(value["scheme"], str)
        and value["scheme"] in {"http", "https"}
        and isinstance(value["host_kind"], str)
        and value["host_kind"] in {"dns", "ipv4", "ipv6"}
        and isinstance(value["host"], str)
        and bool(value["host"])
        and _is_integer(value["effective_port"])
        and 0 <= value["effective_port"] <= 65535
    )


def _valid_path_match(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"type", "values"}
        and value["type"] == "exact_raw_allowlist"
        and isinstance(value["values"], list)
        and all(isinstance(item, str) for item in value["values"])
    )


def _valid_component_match(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"type", "values"}
        and value["type"] == "exact_presence_and_raw_allowlist"
        and isinstance(value["values"], list)
        and all(
            isinstance(item, dict)
            and set(item) == {"present", "raw"}
            and isinstance(item["present"], bool)
            and isinstance(item["raw"], str)
            for item in value["values"]
        )
    )


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _origin_rule_matches(rule: Any, parsed: _ParsedUrl) -> bool:
    if not isinstance(rule, dict):
        return False
    if rule.get("status") != "matched_positive_rule":
        return False
    if set(rule) != _MATCHED_RULE_KEYS:
        return False
    if not (
        isinstance(rule["rule_id"], str)
        and bool(rule["rule_id"])
        and isinstance(rule["rule_version"], str)
        and bool(rule["rule_version"])
        and _valid_origin_identity(rule["origin_identity"])
        and _valid_path_match(rule["path_match"])
        and _valid_component_match(rule["query_match"])
        and _valid_component_match(rule["fragment_match"])
        and rule["public_shareability_established"] is True
        and rule["exact_url_disclosure_grants_access"] is False
        and isinstance(rule["rule_hash"], str)
        and _LOWER_HEX_64_RE.fullmatch(rule["rule_hash"]) is not None
    ):
        return False

    content = dict(rule)
    stored_hash = content.pop("rule_hash")
    envelope = {
        "identity_domain": "trustai.url_origin_rule.v1",
        "rule_id": rule["rule_id"],
        "rule_version": rule["rule_version"],
        "content": content,
    }
    try:
        canonical_rule = _canonical_json(envelope)
    except UnicodeEncodeError:
        return False
    if hashlib.sha256(canonical_rule).hexdigest() != stored_hash:
        return False
    if not _exact_json_equal(rule["origin_identity"], parsed.origin_identity):
        return False
    if parsed.path not in rule["path_match"]["values"]:
        return False
    if not any(
        item["present"] is parsed.query_present and item["raw"] == parsed.query
        for item in rule["query_match"]["values"]
    ):
        return False
    return any(
        item["present"] is parsed.fragment_present and item["raw"] == parsed.fragment
        for item in rule["fragment_match"]["values"]
    )


def _classify_direct(exact_url: Any, auth_context: Any, origin_rule: Any) -> _DirectResult:
    parsed = _parse_url(exact_url)
    reasons = set(parsed.reasons)
    indeterminate = not parsed.valid

    if not isinstance(auth_context, str):
        indeterminate = True
    elif auth_context in _SENSITIVE_AUTH_CONTEXTS:
        reasons.add("authenticated_context")
    elif auth_context != "public_unauthenticated" or auth_context not in _AUTH_CONTEXTS:
        indeterminate = True
    if not _origin_rule_matches(origin_rule, parsed):
        indeterminate = True

    return _DirectResult(frozenset(reasons), indeterminate, parsed.loop_identity)


def _member_direct_result(member: Any) -> _DirectResult:
    if not isinstance(member, dict):
        return _DirectResult(frozenset(), True, None)
    direct = _classify_direct(
        member.get("exact_url"),
        member.get("retrieval_auth_context"),
        member.get("origin_rule"),
    )
    member_input_invalid = (
        not isinstance(member.get("url_role"), str)
        or member.get("url_role") not in _URL_ROLES
        or not isinstance(member.get("restricted_trace_reference"), str)
        or not member.get("restricted_trace_reference")
    )
    return _DirectResult(
        direct.reasons,
        direct.indeterminate or member_input_invalid,
        direct.loop_identity,
    )


def _redirect_analysis(
    *,
    exact_url: Any,
    url_role: Any,
    retrieval_auth_context: Any,
    redirect_context: Any,
    origin_rule: Any,
    restricted_trace_reference: Any,
) -> tuple[bool, bool]:
    if not isinstance(redirect_context, dict) or set(redirect_context) != _REDIRECT_KEYS:
        return False, True

    status = redirect_context["capture_status"]
    current = redirect_context["current_position"]
    requested = redirect_context["requested_position"]
    final = redirect_context["final_position"]
    members = redirect_context["members"]
    topology_valid = (
        isinstance(status, str)
        and status in {"no_redirect", "complete", "incomplete", "ambiguous"}
        and _is_integer(current)
        and _is_integer(requested)
        and _is_integer(final)
        and current >= 0
        and requested >= 0
        and final >= 0
        and isinstance(members, list)
        and bool(members)
    )

    member_results: list[_DirectResult] = []
    if isinstance(members, list):
        for index, member in enumerate(members):
            shape_valid = isinstance(member, dict) and set(member) == _REDIRECT_MEMBER_KEYS
            topology_valid = topology_valid and shape_valid
            if shape_valid:
                topology_valid = topology_valid and _is_integer(member["position"])
                topology_valid = topology_valid and member["position"] == index
                topology_valid = topology_valid and isinstance(member["url_role"], str)
                topology_valid = topology_valid and member["url_role"] in _URL_ROLES
            member_results.append(_member_direct_result(member))

    current_position_valid = (
        isinstance(members, list)
        and _is_integer(current)
        and 0 <= current < len(members)
    )
    if not current_position_valid:
        topology_valid = False
    else:
        current_member = members[current]
        if isinstance(current_member, dict):
            outer = {
                "exact_url": exact_url,
                "url_role": url_role,
                "retrieval_auth_context": retrieval_auth_context,
                "origin_rule": origin_rule,
                "restricted_trace_reference": restricted_trace_reference,
            }
            bound = {key: current_member.get(key) for key in outer}
            topology_valid = topology_valid and _exact_json_equal(outer, bound)
        else:
            topology_valid = False

    if isinstance(members, list) and status == "no_redirect":
        topology_valid = topology_valid and (
            len(members) == 1
            and current == requested == final == 0
            and isinstance(members[0], dict)
            and members[0].get("url_role") == "final_url"
        )
    elif isinstance(members, list) and status == "complete":
        topology_valid = topology_valid and (
            len(members) >= 2
            and requested == 0
            and final == len(members) - 1
            and isinstance(members[0], dict)
            and members[0].get("url_role") == "requested_url"
            and isinstance(members[-1], dict)
            and members[-1].get("url_role") == "final_url"
            and all(
                isinstance(member, dict)
                and member.get("url_role") == "intermediate_redirect_url"
                for member in members[1:-1]
            )
        )
    else:
        topology_valid = False

    sensitive_redirect = status == "complete" and any(
        result.sensitive for result in member_results
    )
    all_public = bool(member_results) and all(result.public_safe for result in member_results)

    loop_detected = False
    seen: set[bytes] = set()
    for result in member_results:
        identity = result.loop_identity
        if identity is None:
            continue
        encoded = _canonical_json(identity)
        if encoded in seen:
            loop_detected = True
        seen.add(encoded)

    indeterminate = not topology_valid or not all_public or loop_detected
    return sensitive_redirect, indeterminate


def validate_url_security(
    exact_url: Any,
    url_role: Any,
    retrieval_auth_context: Any,
    redirect_context: Any,
    origin_rule: Any,
    restricted_trace_reference: Any,
) -> dict[str, Any]:
    """Classify one captured URL position under ``url_security_policy_v1@v1``."""

    direct = _classify_direct(exact_url, retrieval_auth_context, origin_rule)
    reasons = set(direct.reasons)
    indeterminate = direct.indeterminate
    if not isinstance(url_role, str) or url_role not in _URL_ROLES:
        indeterminate = True
    if not isinstance(restricted_trace_reference, str) or not restricted_trace_reference:
        indeterminate = True

    redirect_sensitive, redirect_indeterminate = _redirect_analysis(
        exact_url=exact_url,
        url_role=url_role,
        retrieval_auth_context=retrieval_auth_context,
        redirect_context=redirect_context,
        origin_rule=origin_rule,
        restricted_trace_reference=restricted_trace_reference,
    )
    if redirect_sensitive:
        reasons.add("sensitive_redirect_context")
    indeterminate = indeterminate or redirect_indeterminate

    selected_reason = next((reason for reason in _REASON_PRECEDENCE if reason in reasons), None)
    if selected_reason is not None:
        classification = "sensitive"
        reason_codes = [selected_reason]
    elif indeterminate:
        classification = "indeterminate"
        reason_codes = ["public_shareability_indeterminate"]
    else:
        classification = "public_safe"
        reason_codes = []

    return {
        "classification": classification,
        "reason_codes": reason_codes,
        "url_role": url_role,
        "restricted_trace_reference": restricted_trace_reference,
        "policy_id": _POLICY_ID,
        "policy_version": _POLICY_VERSION,
        "policy_hash": _POLICY_HASH,
    }
