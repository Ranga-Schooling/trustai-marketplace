"""Fixed-contract canonical validation for the frozen evaluation schemas.

This is deliberately not a general-purpose JSON Schema implementation. It
evaluates only the closed Draft 2020-12 keyword profile used by the exact
hash-pinned V1 schema set and fails closed if that contract changes.
"""

from __future__ import annotations

import calendar
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import ipaddress
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping

from app.services.evaluation_contract_identity import (
    ContractIdentityError,
    load_strict_contract_json,
    verify_output_schema_artifact,
)
from app.services.evaluation_resource_limits import RESOURCE_LIMIT_VALUES
from app.services.normalization_parser import (
    AdmittedJsonNumber,
    CanonicalSemanticJson,
    ExactJsonNumber,
    NumericDomainAdmission,
    admit_exact_json_number,
    canonicalize_semantic_json,
    replay_canonical_semantic_json,
)


OUTPUT_SCHEMA_SET_SHA256 = (
    "125809d08e911d51b4619002f02a969b03b8da5866bfab1b8346758c0bb9a6f4"
)
OUTPUT_SCHEMA_IDS = (
    "text_output_schema_v1",
    "retrieval_evidence_bundle_v1",
    "search_output_schema_v1",
    "visual_output_schema_v1",
)
WORKLOAD_SCHEMA_IDS = MappingProxyType(
    {
        "text_risk_analysis": "text_output_schema_v1",
        "grounded_product_price_research_retrieval": (
            "retrieval_evidence_bundle_v1"
        ),
        "grounded_product_price_research_synthesis": "search_output_schema_v1",
        "visual_inspection": "visual_output_schema_v1",
    }
)
_DIALECT = "https://json-schema.org/draft/2020-12/schema"
_FORMATS = ("uri", "date-time")
_SUPPORTED_KEYWORDS = frozenset(
    {
        "$id",
        "$schema",
        "additionalProperties",
        "allOf",
        "anyOf",
        "const",
        "contains",
        "enum",
        "format",
        "if",
        "items",
        "maxItems",
        "maxLength",
        "maximum",
        "minContains",
        "minItems",
        "minLength",
        "minimum",
        "not",
        "oneOf",
        "pattern",
        "properties",
        "required",
        "then",
        "type",
        "uniqueItems",
    }
)
_EXPECTED_SCHEMA_HASHES = {
    "text_output_schema_v1": (
        "baec020db56ab334659a9f278a7383d7b3b4860275ae7276ad6a39bb1c26d37d"
    ),
    "retrieval_evidence_bundle_v1": (
        "a823c58173370aa2eb5e87bf96decec6c5b3a413e96aefc41783968181932201"
    ),
    "search_output_schema_v1": (
        "d66cc128a778577c2860b74cf7670eb8fb7f9d7b144df52e7258276169142c05"
    ),
    "visual_output_schema_v1": (
        "f085eb944710362f18add95bd9b64af8088edaa55cf1838ff4ec995ee0f3f5e3"
    ),
}
_TYPES = frozenset(
    {"array", "boolean", "integer", "null", "number", "object", "string"}
)
_PATTERNS = frozenset(
    {
        "^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
        "^[A-Z]{3}$",
        "\\S",
    }
)
_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_CURRENCY_PATTERN = re.compile(r"[A-Z]{3}\Z")
_DATETIME_PATTERN = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})T"
    r"([0-9]{2}):([0-9]{2}):([0-9]{2})\.([0-9]{3})Z\Z"
)
_URI_PATTERN = re.compile(
    r"(?P<scheme>https?)://"
    r"(?P<authority>[^/?#]*)"
    r"(?P<path>[^?#]*)"
    r"(?:\?(?P<query>[^#]*))?"
    r"(?:#(?P<fragment>.*))?\Z",
    re.IGNORECASE | re.ASCII,
)
_PCT_ENCODED = r"%[0-9A-Fa-f]{2}"
_UNRESERVED = r"A-Za-z0-9._~\-"
_SUB_DELIMS = r"!$&'()*+,;="
_USERINFO_PATTERN = re.compile(
    rf"(?:[{_UNRESERVED}{re.escape(_SUB_DELIMS)}:]|{_PCT_ENCODED})*\Z"
)
_REG_NAME_PATTERN = re.compile(
    rf"(?:[{_UNRESERVED}{re.escape(_SUB_DELIMS)}]|{_PCT_ENCODED})+\Z"
)
_PORT_PATTERN = re.compile(r"[0-9]*\Z")
_PCHAR = rf"[{_UNRESERVED}{re.escape(_SUB_DELIMS)}:@]|{_PCT_ENCODED}"
_PATH_PATTERN = re.compile(rf"(?:{_PCHAR}|/)*\Z")
_QUERY_FRAGMENT_PATTERN = re.compile(rf"(?:{_PCHAR}|[/?])*\Z")
_IPV_FUTURE_PATTERN = re.compile(
    rf"[vV][0-9A-Fa-f]+\.(?:[{_UNRESERVED}{re.escape(_SUB_DELIMS)}:])+\Z"
)
_ECMASCRIPT_WHITESPACE = frozenset(
    {
        "\u0009",
        "\u000a",
        "\u000b",
        "\u000c",
        "\u000d",
        "\u0020",
        "\u00a0",
        "\u1680",
        "\u2000",
        "\u2001",
        "\u2002",
        "\u2003",
        "\u2004",
        "\u2005",
        "\u2006",
        "\u2007",
        "\u2008",
        "\u2009",
        "\u200a",
        "\u2028",
        "\u2029",
        "\u202f",
        "\u205f",
        "\u3000",
        "\ufeff",
    }
)


class SchemaContractError(ValueError):
    """The immutable application-owned schema contract cannot be executed."""

    terminal_outcome = "internal_harness_error"


class CanonicalSchemaValidationError(ValueError):
    """One canonical candidate failed the frozen schema boundary safely."""

    validator_id = "canonical_schema_validation"
    terminal_outcome = "failed_canonical_validation"

    def __init__(
        self,
        *,
        schema_id: str,
        keyword: str,
        path: tuple[str | int, ...],
    ) -> None:
        super().__init__(f"{self.validator_id}:{schema_id}:{keyword}")
        self.schema_id = schema_id
        self.keyword = keyword
        self.path = path


class SchemaValidatedCandidate:
    """A canonical semantic value that passed one pinned schema record."""

    __slots__ = (
        "_admitted_value",
        "_canonical_bytes",
        "_semantic_hash",
        "schema_id",
        "schema_set_sha256",
        "schema_sha256",
    )

    def __init__(
        self,
        *,
        schema_id: str,
        schema_sha256: str,
        schema_set_sha256: str,
        canonical_semantic_json: CanonicalSemanticJson,
        _validation_token: object | None = None,
    ) -> None:
        if _validation_token is not _SCHEMA_VALIDATION_TOKEN:
            raise TypeError("SchemaValidatedCandidate requires registry validation")
        object.__setattr__(self, "schema_id", schema_id)
        object.__setattr__(self, "schema_sha256", schema_sha256)
        object.__setattr__(self, "schema_set_sha256", schema_set_sha256)
        object.__setattr__(
            self,
            "_admitted_value",
            _freeze_json_tree(canonical_semantic_json.admitted.value),
        )
        object.__setattr__(
            self,
            "_canonical_bytes",
            canonical_semantic_json.canonical_bytes,
        )
        object.__setattr__(
            self,
            "_semantic_hash",
            canonical_semantic_json.strict_parsed_semantic_payload_hash,
        )

    def __setattr__(self, _name: str, _value: Any) -> None:
        raise AttributeError("SchemaValidatedCandidate is immutable")

    @property
    def canonical_semantic_json(self) -> CanonicalSemanticJson:
        """Return a detached reconstruction of the validated canonical value."""
        if hashlib.sha256(self._canonical_bytes).hexdigest() != self._semantic_hash:
            raise SchemaContractError("validated_candidate_identity")
        return CanonicalSemanticJson(
            admitted=NumericDomainAdmission(_thaw_json_tree(self._admitted_value)),
            canonical_bytes=self._canonical_bytes,
            strict_parsed_semantic_payload_hash=self._semantic_hash,
        )

    def __repr__(self) -> str:
        return (
            "SchemaValidatedCandidate("
            f"schema_id={self.schema_id!r}, "
            f"schema_sha256={self.schema_sha256!r}, "
            f"schema_set_sha256={self.schema_set_sha256!r})"
        )


_SCHEMA_VALIDATION_TOKEN = object()


class CanonicalOutputSchemaRegistry:
    """Verified fixed registry for the exact four frozen output schemas."""

    __slots__ = ("_schemas", "schema_set_sha256")

    def __init__(self, artifact: dict[str, Any]) -> None:
        if type(artifact) is not dict:
            raise SchemaContractError("output_schema_artifact_type")
        artifact_snapshot = deepcopy(artifact)
        try:
            identity = verify_output_schema_artifact(artifact_snapshot)
        except (ContractIdentityError, KeyError, TypeError, ValueError) as exc:
            raise SchemaContractError("output_schema_identity") from exc
        if identity.set_hash != OUTPUT_SCHEMA_SET_SHA256:
            raise SchemaContractError("output_schema_set_hash")
        if artifact_snapshot.get("json_schema_dialect") != _DIALECT:
            raise SchemaContractError("output_schema_dialect")
        if artifact_snapshot.get("schema_order") != list(OUTPUT_SCHEMA_IDS):
            raise SchemaContractError("output_schema_inventory")
        if dict(identity.child_hashes) != _EXPECTED_SCHEMA_HASHES:
            raise SchemaContractError("output_schema_child_hashes")
        self._validate_format_policy(artifact_snapshot)

        records = artifact_snapshot.get("schemas")
        if not isinstance(records, list):
            raise SchemaContractError("output_schema_records")
        schemas: dict[str, Mapping[str, Any]] = {}
        observed_keywords: set[str] = set()
        for record in records:
            if not isinstance(record, dict):
                raise SchemaContractError("output_schema_record")
            schema_id = record.get("schema_id")
            schema = record.get("schema")
            if schema_id not in OUTPUT_SCHEMA_IDS or not isinstance(schema, dict):
                raise SchemaContractError("output_schema_record_identity")
            expected_workload = next(
                workload
                for workload, expected_schema_id in WORKLOAD_SCHEMA_IDS.items()
                if expected_schema_id == schema_id
            )
            if record.get("workload_or_stage") != expected_workload:
                raise SchemaContractError("output_schema_workload_binding")
            self._validate_schema_definition(schema, observed_keywords, root=True)
            schemas[schema_id] = _freeze_json_tree(record)
        if tuple(schemas) != OUTPUT_SCHEMA_IDS:
            raise SchemaContractError("output_schema_record_order")
        if observed_keywords != _SUPPORTED_KEYWORDS:
            raise SchemaContractError("output_schema_keyword_profile")
        object.__setattr__(self, "_schemas", MappingProxyType(schemas))
        object.__setattr__(self, "schema_set_sha256", identity.set_hash)

    def __setattr__(self, _name: str, _value: Any) -> None:
        raise AttributeError("CanonicalOutputSchemaRegistry is immutable")

    @classmethod
    def from_path(
        cls,
        artifact_path: str | Path,
    ) -> CanonicalOutputSchemaRegistry:
        """Load the application-owned schema artifact through strict JSON."""
        try:
            artifact = load_strict_contract_json(artifact_path)
        except (OSError, TypeError, ValueError) as exc:
            raise SchemaContractError("output_schema_artifact_load") from exc
        return cls(artifact)

    @classmethod
    def from_artifact(
        cls,
        artifact: dict[str, Any],
    ) -> CanonicalOutputSchemaRegistry:
        """Build a registry only after exact identity and profile validation."""
        if not isinstance(artifact, dict):
            raise SchemaContractError("output_schema_artifact_type")
        return cls(artifact)

    @property
    def schema_ids(self) -> tuple[str, ...]:
        return tuple(self._schemas)

    def validate(
        self,
        schema_id: str,
        canonical_semantic_json: CanonicalSemanticJson,
    ) -> SchemaValidatedCandidate:
        """Validate without coercion, repair, defaults, or semantic mutation."""
        if type(schema_id) is not str or schema_id not in self._schemas:
            raise SchemaContractError("unknown_schema_id")
        if not isinstance(canonical_semantic_json, CanonicalSemanticJson):
            raise TypeError("canonical_semantic_json must be CanonicalSemanticJson")
        try:
            reconstructed = canonicalize_semantic_json(
                canonical_semantic_json.admitted
            )
            _verify_admitted_number_identity(canonical_semantic_json.admitted.value)
            detached = replay_canonical_semantic_json(
                canonical_semantic_json.canonical_bytes
            )
        except (RuntimeError, TypeError, ValueError):
            raise SchemaContractError("canonical_semantic_json_identity") from None
        if (
            reconstructed.canonical_bytes != canonical_semantic_json.canonical_bytes
            or reconstructed.strict_parsed_semantic_payload_hash
            != canonical_semantic_json.strict_parsed_semantic_payload_hash
            or hashlib.sha256(canonical_semantic_json.canonical_bytes).hexdigest()
            != canonical_semantic_json.strict_parsed_semantic_payload_hash
            or not _json_equal(
                reconstructed.admitted.value,
                detached.admitted.value,
            )
        ):
            raise SchemaContractError("canonical_semantic_json_identity")
        record = self._schemas[schema_id]
        try:
            _validate_instance(
                detached.admitted.value,
                record["schema"],
                (),
            )
        except _ValidationFailure as exc:
            raise CanonicalSchemaValidationError(
                schema_id=schema_id,
                keyword=exc.keyword,
                path=exc.path,
            ) from None
        return SchemaValidatedCandidate(
            schema_id=schema_id,
            schema_sha256=record["schema_sha256"],
            schema_set_sha256=self.schema_set_sha256,
            canonical_semantic_json=detached,
            _validation_token=_SCHEMA_VALIDATION_TOKEN,
        )

    def validate_workload(
        self,
        workload_or_stage: str,
        canonical_semantic_json: CanonicalSemanticJson,
    ) -> SchemaValidatedCandidate:
        """Select the application-owned schema from the frozen workload map."""
        if (
            type(workload_or_stage) is not str
            or workload_or_stage not in WORKLOAD_SCHEMA_IDS
        ):
            raise SchemaContractError("unknown_workload_or_stage")
        return self.validate(
            WORKLOAD_SCHEMA_IDS[workload_or_stage],
            canonical_semantic_json,
        )

    @staticmethod
    def _validate_format_policy(artifact: dict[str, Any]) -> None:
        policies = artifact.get("global_policies")
        if not isinstance(policies, dict):
            raise SchemaContractError("output_schema_global_policies")
        policy = policies.get("format_assertion")
        if not isinstance(policy, dict):
            raise SchemaContractError("format_assertion_policy")
        if (
            policy.get("format_assertion_required") is not True
            or policy.get("asserted_formats") != list(_FORMATS)
            or policy.get("failure_result")
            != (
                "A value that fails an asserted format is a canonical schema "
                "validation failure."
            )
        ):
            raise SchemaContractError("format_assertion_policy")

    @classmethod
    def _validate_schema_definition(
        cls,
        schema: Any,
        observed_keywords: set[str],
        *,
        root: bool = False,
    ) -> None:
        if not isinstance(schema, dict) or not schema:
            raise SchemaContractError("schema_definition")
        unknown = set(schema) - _SUPPORTED_KEYWORDS
        if unknown:
            raise SchemaContractError("unsupported_schema_keyword")
        observed_keywords.update(schema)
        if root and (
            schema.get("$schema") != _DIALECT
            or not isinstance(schema.get("$id"), str)
        ):
            raise SchemaContractError("schema_root_identity")
        schema_type = schema.get("type")
        if schema_type is not None and schema_type not in _TYPES:
            raise SchemaContractError("schema_type")
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            raise SchemaContractError("schema_properties")
        for child in properties.values():
            cls._validate_schema_definition(child, observed_keywords)
        required = schema.get("required", [])
        if (
            not isinstance(required, list)
            or any(type(field_name) is not str for field_name in required)
            or len(required) != len(set(required))
        ):
            raise SchemaContractError("schema_required")
        if "additionalProperties" in schema and type(
            schema["additionalProperties"]
        ) is not bool:
            raise SchemaContractError("schema_additional_properties")
        if "items" in schema:
            cls._validate_schema_definition(schema["items"], observed_keywords)
        for keyword in ("allOf", "anyOf", "oneOf"):
            if keyword in schema:
                children = schema[keyword]
                if not isinstance(children, list) or not children:
                    raise SchemaContractError(f"schema_{keyword}")
                for child in children:
                    cls._validate_schema_definition(child, observed_keywords)
        for keyword in ("contains", "if", "not", "then"):
            if keyword in schema:
                cls._validate_schema_definition(schema[keyword], observed_keywords)
        if "then" in schema and "if" not in schema:
            raise SchemaContractError("schema_then_without_if")
        if "if" in schema and "then" not in schema:
            raise SchemaContractError("schema_if_without_then")
        if "minContains" in schema and "contains" not in schema:
            raise SchemaContractError("schema_min_contains")
        for keyword in (
            "maxItems",
            "maxLength",
            "minContains",
            "minItems",
            "minLength",
        ):
            if keyword in schema and (
                type(schema[keyword]) is not int or schema[keyword] < 0
            ):
                raise SchemaContractError(f"schema_{keyword}")
        for keyword in ("minimum", "maximum"):
            if keyword in schema and (
                isinstance(schema[keyword], bool)
                or type(schema[keyword]) not in {int, float}
            ):
                raise SchemaContractError(f"schema_{keyword}")
        if "uniqueItems" in schema and type(schema["uniqueItems"]) is not bool:
            raise SchemaContractError("schema_unique_items")
        if "pattern" in schema and schema["pattern"] not in _PATTERNS:
            raise SchemaContractError("unsupported_schema_pattern")
        if "format" in schema and schema["format"] not in _FORMATS:
            raise SchemaContractError("unsupported_schema_format")
        if "enum" in schema and (
            not isinstance(schema["enum"], list) or not schema["enum"]
        ):
            raise SchemaContractError("schema_enum")


def _freeze_json_tree(value: Any) -> Any:
    if type(value) is dict:
        return MappingProxyType(
            {key: _freeze_json_tree(child) for key, child in value.items()}
        )
    if type(value) is list:
        return tuple(_freeze_json_tree(child) for child in value)
    return value


def _thaw_json_tree(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json_tree(child) for key, child in value.items()}
    if type(value) is tuple:
        return [_thaw_json_tree(child) for child in value]
    return value


def _verify_admitted_number_identity(value: Any) -> None:
    maximum_children = (
        RESOURCE_LIMIT_VALUES["maximum_total_object_members"]
        + RESOURCE_LIMIT_VALUES["maximum_total_array_elements"]
    )
    observed_children = 0
    active_container_ids: set[int] = set()
    pending: list[tuple[str, Any]] = [("enter", value)]
    while pending:
        operation, current = pending.pop()
        if operation == "exit":
            active_container_ids.remove(id(current))
            continue
        if isinstance(current, AdmittedJsonNumber):
            expected = admit_exact_json_number(
                ExactJsonNumber(
                    lexeme=current.lexeme,
                    exact_decimal=current.exact_decimal,
                )
            )
            if current != expected:
                raise SchemaContractError("canonical_semantic_json_identity")
        elif type(current) in {dict, list}:
            if id(current) in active_container_ids:
                raise SchemaContractError("canonical_semantic_json_identity")
            active_container_ids.add(id(current))
            children = (
                tuple(current.values()) if type(current) is dict else tuple(current)
            )
            observed_children += len(children)
            if observed_children > maximum_children:
                raise SchemaContractError("canonical_semantic_json_identity")
            pending.append(("exit", current))
            pending.extend(("enter", child) for child in reversed(children))


@dataclass(frozen=True, slots=True)
class _ValidationFailure(Exception):
    keyword: str
    path: tuple[str | int, ...]


def _fail(keyword: str, path: tuple[str | int, ...]) -> None:
    raise _ValidationFailure(keyword, path)


def _instance_type_matches(instance: Any, expected: str) -> bool:
    if expected == "object":
        return type(instance) is dict
    if expected == "array":
        return type(instance) is list
    if expected == "string":
        return type(instance) is str
    if expected == "boolean":
        return type(instance) is bool
    if expected == "null":
        return instance is None
    if expected == "number":
        return isinstance(instance, AdmittedJsonNumber)
    if expected == "integer":
        return (
            isinstance(instance, AdmittedJsonNumber)
            and instance.mathematical_integer
        )
    raise SchemaContractError("unsupported_runtime_schema_type")


def _numeric_decimal(value: Any) -> Decimal | None:
    if isinstance(value, AdmittedJsonNumber):
        return value.exact_decimal
    if type(value) is int:
        return Decimal(value)
    if type(value) is float:
        return Decimal(str(value))
    return None


def _json_equal(left: Any, right: Any) -> bool:
    left_number = _numeric_decimal(left)
    right_number = _numeric_decimal(right)
    if left_number is not None or right_number is not None:
        return (
            left_number is not None
            and right_number is not None
            and left_number == right_number
        )
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(
            _json_equal(left[key], right[key]) for key in left
        )
    if type(left) is list:
        return len(left) == len(right) and all(
            _json_equal(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    return left == right


def _is_valid(schema: dict[str, Any], instance: Any) -> bool:
    try:
        _validate_instance(instance, schema, ())
    except _ValidationFailure:
        return False
    return True


def _validate_instance(
    instance: Any,
    schema: Mapping[str, Any],
    path: tuple[str | int, ...],
) -> None:
    expected_type = schema.get("type")
    if expected_type is not None and not _instance_type_matches(
        instance,
        expected_type,
    ):
        _fail("type", path)

    if "enum" in schema and not any(
        _json_equal(instance, allowed) for allowed in schema["enum"]
    ):
        _fail("enum", path)
    if "const" in schema and not _json_equal(instance, schema["const"]):
        _fail("const", path)

    if type(instance) is dict:
        required = schema.get("required", [])
        if any(field_name not in instance for field_name in required):
            _fail("required", path)
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and any(
            field_name not in properties for field_name in instance
        ):
            _fail("additionalProperties", path)
        for field_name, child_schema in properties.items():
            if field_name in instance:
                _validate_instance(
                    instance[field_name],
                    child_schema,
                    (*path, field_name),
                )

    if type(instance) is list:
        if len(instance) < schema.get("minItems", 0):
            _fail("minItems", path)
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            _fail("maxItems", path)
        if schema.get("uniqueItems") is True:
            for index, item in enumerate(instance):
                if any(_json_equal(item, prior) for prior in instance[:index]):
                    _fail("uniqueItems", (*path, index))
        if "items" in schema:
            for index, item in enumerate(instance):
                _validate_instance(item, schema["items"], (*path, index))
        if "contains" in schema:
            match_count = sum(
                _is_valid(schema["contains"], item) for item in instance
            )
            if match_count < schema.get("minContains", 1):
                _fail("contains", path)

    if type(instance) is str:
        if len(instance) < schema.get("minLength", 0):
            _fail("minLength", path)
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            _fail("maxLength", path)
        if "pattern" in schema and not _pattern_matches(schema["pattern"], instance):
            _fail("pattern", path)
        if "format" in schema and not _format_matches(schema["format"], instance):
            _fail("format", path)

    number = _numeric_decimal(instance)
    if number is not None:
        if "minimum" in schema and number < Decimal(str(schema["minimum"])):
            _fail("minimum", path)
        if "maximum" in schema and number > Decimal(str(schema["maximum"])):
            _fail("maximum", path)

    for child in schema.get("allOf", []):
        _validate_instance(instance, child, path)
    if "anyOf" in schema and not any(
        _is_valid(child, instance) for child in schema["anyOf"]
    ):
        _fail("anyOf", path)
    if "oneOf" in schema and sum(
        _is_valid(child, instance) for child in schema["oneOf"]
    ) != 1:
        _fail("oneOf", path)
    if "not" in schema and _is_valid(schema["not"], instance):
        _fail("not", path)
    if "if" in schema and _is_valid(schema["if"], instance):
        _validate_instance(instance, schema["then"], path)


def _pattern_matches(pattern: str, value: str) -> bool:
    if pattern == "^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$":
        return _ID_PATTERN.fullmatch(value) is not None
    if pattern == "^[A-Z]{3}$":
        return _CURRENCY_PATTERN.fullmatch(value) is not None
    if pattern == "\\S":
        return any(character not in _ECMASCRIPT_WHITESPACE for character in value)
    raise SchemaContractError("unsupported_runtime_schema_pattern")


def _format_matches(format_name: str, value: str) -> bool:
    if format_name == "uri":
        return _is_absolute_http_uri(value)
    if format_name == "date-time":
        return _is_canonical_utc_datetime(value)
    raise SchemaContractError("unsupported_runtime_schema_format")


def _is_absolute_http_uri(value: str) -> bool:
    """Assert RFC 3986 URI syntax plus the frozen absolute HTTP(S) rule."""
    matched = _URI_PATTERN.fullmatch(value)
    if matched is None:
        return False
    authority = matched.group("authority")
    if authority.count("@") > 1:
        return False
    if "@" in authority:
        userinfo, host_port = authority.split("@", 1)
        if _USERINFO_PATTERN.fullmatch(userinfo) is None:
            return False
    else:
        host_port = authority
    if host_port.startswith("["):
        closing_bracket = host_port.find("]")
        if closing_bracket < 0:
            return False
        host = host_port[1:closing_bracket]
        remainder = host_port[closing_bracket + 1 :]
        if remainder and not remainder.startswith(":"):
            return False
        port = remainder[1:] if remainder else None
        if not _is_ip_literal(host):
            return False
    else:
        if host_port.count(":") > 1:
            return False
        if ":" in host_port:
            host, port = host_port.rsplit(":", 1)
        else:
            host, port = host_port, None
        if _REG_NAME_PATTERN.fullmatch(host) is None:
            return False
    if port is not None and _PORT_PATTERN.fullmatch(port) is None:
        return False
    path = matched.group("path")
    if path and not path.startswith("/"):
        return False
    if _PATH_PATTERN.fullmatch(path) is None:
        return False
    query = matched.group("query")
    if query is not None and _QUERY_FRAGMENT_PATTERN.fullmatch(query) is None:
        return False
    fragment = matched.group("fragment")
    return fragment is None or _QUERY_FRAGMENT_PATTERN.fullmatch(fragment) is not None


def _is_ip_literal(host: str) -> bool:
    if _IPV_FUTURE_PATTERN.fullmatch(host) is not None:
        return True
    if "%" in host:
        return False
    try:
        ipaddress.IPv6Address(host)
    except ValueError:
        return False
    return True


def _is_canonical_utc_datetime(value: str) -> bool:
    matched = _DATETIME_PATTERN.fullmatch(value)
    if matched is None:
        return False
    year, month, day, hour, minute, second, _millisecond = map(
        int,
        matched.groups(),
    )
    if year == 0 or month < 1 or month > 12:
        return False
    if day < 1 or day > calendar.monthrange(year, month)[1]:
        return False
    if hour > 23 or minute > 59 or second > 60:
        return False
    if second == 60 and not (
        hour == 23
        and minute == 59
        and (month, day) in {(6, 30), (12, 31)}
    ):
        return False
    return True
