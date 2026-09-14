"""Pilot-minimal, provider-free PS1 trace-backed evidence construction.

Provider-native search is discovery only.  Canonical evidence is produced only
from an application-owned refetch observation whose complete URL trace passes
the frozen URL-security policy.  This module performs no network, provider,
credential, persistence, scoring, or execution-authority operation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from app.services.evaluation_contract_identity import (
    ContractIdentityError,
    load_strict_contract_json,
)
from app.services.evaluation_data_handling import (
    RestrictedTraceReference,
    RestrictedUrlTrace,
    capture_restricted_url_trace,
)
from app.services.evaluation_resource_limits import RESOURCE_LIMIT_VALUES
from app.services.evaluation_retrieval_trace import (
    RetrievalAllocationPlan,
    RetrievalEvidenceObservation,
    RetrievalSourceObservation,
    ValidatedTracePositionInventory,
    allocate_retrieval_observations,
    derive_public_safe_deduplication_key,
    validate_trace_position_inventory,
)
from app.services.evaluation_schema_validation import CanonicalOutputSchemaRegistry
from app.services.evaluation_validators import validate_retrieval_status_coherence
from app.services.normalization_parser import normalize_semantic_json
from app.services.url_security import validate_url_security


_ROOT = Path(__file__).resolve().parents[3]
_ARTIFACTS = _ROOT / "docs" / "testing" / "ai-evaluation"
_SOURCE_CLASSIFICATION_PATH = _ARTIFACTS / "source-classification-policy.v1.json"
_ORIGIN_REGISTRY_PATH = (
    _ARTIFACTS / "url-security-operational-origin-rule-registry.v1.json"
)
_OBJECTIVE_SUPPORT_PATH = (
    _ARTIFACTS / "retrieval-objective-support-policy.v1.json"
)
_EVIDENCE_EXTRACTOR_PATH = _ARTIFACTS / "trace-backed-evidence-extractor.v1.json"
_OUTPUT_SCHEMA_PATH = _ARTIFACTS / "output-schemas.v1.json"

SOURCE_CLASSIFICATION_POLICY_HASH = (
    "74fba39bc0f1050a790758bc9cb74ea41392a79957e5f33b2b43648e2ae2a937"
)
ORIGIN_RULE_REGISTRY_HASH = (
    "dd93fb8942742cc0677c757ff3f3b0bede03249daa24b9a6dcbb28242d869171"
)
OBJECTIVE_SUPPORT_POLICY_HASH = (
    "73a0061d1a35280eaf3714b9aeeec83499c9178b5d7452f046d14ed4785579c9"
)
EVIDENCE_EXTRACTOR_POLICY_HASH = (
    "6edba168ac7b40dde16936e8492f58d71f8eefde7ee2980f465af3d629a2f2de"
)

_SOURCE_TYPES = (
    "manufacturer",
    "authorized_retailer",
    "established_retailer",
    "marketplace_active",
    "marketplace_completed",
    "reputable_secondary",
    "forum_or_social",
    "affiliate_or_seo",
    "scraped_aggregator",
    "other",
)
_SUPPORTED_SOURCE_TYPES = ("manufacturer", "established_retailer")
_EVIDENCE_TYPES = (
    "identity",
    "status",
    "specification",
    "price",
    "availability",
    "condition",
    "warranty",
    "bundle",
    "regional_context",
    "other_material",
)
_PRICE = re.compile(r"(?<![A-Za-z0-9_])\$[0-9]{1,4}\.[0-9]{2}(?![0-9])")
_CONFLICT_MARKERS = (
    "MX Master 3S For Mac",
    "910-006570",
    "910-007500",
    "Bluetooth Edition",
)
_DISCOVERY_TOKEN = object()
_ASSEMBLY_TOKEN = object()


class Ps1ContractError(ValueError):
    """A PS1 contract, trace, evidence, or support invariant failed closed."""


def _fail(code: str) -> Ps1ContractError:
    return Ps1ContractError(code)


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise _fail("canonical_json") from exc


def _json_copy(value: Any) -> Any:
    return json.loads(_canonical_bytes(value).decode("utf-8"))


def _semantic_hash(artifact: dict[str, Any]) -> str:
    detached = _json_copy(artifact)
    try:
        detached["specification_identity"]["semantic_hash"] = None
    except (KeyError, TypeError) as exc:
        raise _fail("contract_identity") from exc
    return hashlib.sha256(_canonical_bytes(detached)).hexdigest()


def _execution_blocked(artifact: dict[str, Any]) -> bool:
    execution = artifact.get("execution_boundary")
    return isinstance(execution, dict) and execution == {
        "execution_state": "blocked_pre_execution",
        "provider_calls_allowed": False,
        "pilot_calls_allowed": False,
        "scored_calls_allowed": False,
        "provider_calls_completed": 0,
        "pilot_calls_completed": 0,
        "scored_calls_completed": 0,
        "winner_selected": False,
        "this_artifact_independently_authorizes_execution": False,
    }


@dataclass(frozen=True, slots=True)
class Ps1PolicyIdentity:
    policy_id: str
    policy_version: str
    policy_hash: str


@dataclass(frozen=True, slots=True)
class SourceClassificationContract(Ps1PolicyIdentity):
    supported_source_types: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OriginRegistryContract(Ps1PolicyIdentity):
    rule_count: int
    pilot_origins: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ObjectiveSupportContract(Ps1PolicyIdentity):
    objective_count: int
    material_objective_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceExtractorContract(Ps1PolicyIdentity):
    trace_backed_only: bool


@dataclass(frozen=True, slots=True)
class Ps1Contracts:
    source_classification: SourceClassificationContract
    origin_registry: OriginRegistryContract
    objective_support: ObjectiveSupportContract
    evidence_extractor: EvidenceExtractorContract
    provider_calls_allowed: bool = False


def _load(path: str | Path) -> dict[str, Any]:
    try:
        artifact = load_strict_contract_json(path)
    except (ContractIdentityError, OSError, TypeError, ValueError) as exc:
        raise _fail("contract_load") from exc
    if type(artifact) is not dict:
        raise _fail("contract_shape")
    return artifact


def _verify_common(
    artifact: dict[str, Any],
    *,
    policy_id: str,
    expected_hash: str | None,
) -> str:
    if (
        artifact.get("artifact_id") != policy_id
        or artifact.get("artifact_version") != "v1"
        or artifact.get("status") != "frozen"
        or artifact.get("provider_neutral") is not True
        or not _execution_blocked(artifact)
    ):
        raise _fail("contract_shape")
    actual = _semantic_hash(artifact)
    stored = artifact.get("specification_identity", {}).get("semantic_hash")
    if stored != actual or (expected_hash is not None and actual != expected_hash):
        raise _fail("contract_identity")
    return actual


def _rule_hash(rule: dict[str, Any]) -> str:
    content = deepcopy(rule)
    stored = content.pop("rule_hash", None)
    envelope = {
        "identity_domain": "trustai.url_origin_rule.v1",
        "rule_id": content.get("rule_id"),
        "rule_version": content.get("rule_version"),
        "content": content,
    }
    actual = hashlib.sha256(_canonical_bytes(envelope)).hexdigest()
    if stored != actual:
        raise _fail("origin_rule_identity")
    return actual


def _verify_source_classification(path: str | Path) -> SourceClassificationContract:
    artifact = _load(path)
    actual = _verify_common(
        artifact,
        policy_id="source_classification_policy_v1",
        expected_hash=(
            SOURCE_CLASSIFICATION_POLICY_HASH
            if Path(path) == _SOURCE_CLASSIFICATION_PATH
            else None
        ),
    )
    if (
        tuple(artifact.get("source_type_vocabulary", ())) != _SOURCE_TYPES
        or tuple(artifact.get("supported_deterministic_source_types", ()))
        != _SUPPORTED_SOURCE_TYPES
        or tuple(item.get("source_type") for item in artifact.get("rules", ()))
        != _SUPPORTED_SOURCE_TYPES
        or artifact.get("failure_policy", {}).get("fallback_to_other_allowed")
        is not False
    ):
        raise _fail("source_classification_contract")
    return SourceClassificationContract(
        policy_id=artifact["artifact_id"],
        policy_version=artifact["artifact_version"],
        policy_hash=actual,
        supported_source_types=_SUPPORTED_SOURCE_TYPES,
    )


def _verify_origin_registry(path: str | Path) -> OriginRegistryContract:
    artifact = _load(path)
    entries = artifact.get("registry_entries")
    if type(entries) is not list or len(entries) != 2:
        raise _fail("origin_registry_inventory")
    seen_ids: set[str] = set()
    for entry in entries:
        if (
            type(entry) is not dict
            or entry.get("registry_entry_id") in seen_ids
            or entry.get("source_type") not in _SUPPORTED_SOURCE_TYPES
            or type(entry.get("origin_rule")) is not dict
        ):
            raise _fail("origin_registry_entry")
        seen_ids.add(entry["registry_entry_id"])
        if entry["origin_rule"].get("rule_id") != entry["registry_entry_id"]:
            raise _fail("origin_registry_entry")
        _rule_hash(entry["origin_rule"])
    actual = _verify_common(
        artifact,
        policy_id="url_security_operational_origin_rule_registry_v1",
        expected_hash=(
            ORIGIN_RULE_REGISTRY_HASH if Path(path) == _ORIGIN_REGISTRY_PATH else None
        ),
    )
    return OriginRegistryContract(
        policy_id=artifact["artifact_id"],
        policy_version=artifact["artifact_version"],
        policy_hash=actual,
        rule_count=len(entries),
        pilot_origins=tuple(entry["pilot_origin"] for entry in entries),
    )


def _verify_objective_support(path: str | Path) -> ObjectiveSupportContract:
    artifact = _load(path)
    objectives = artifact.get("ps1_objective_manifest", {}).get("objectives")
    if type(objectives) is not list or len(objectives) != 3:
        raise _fail("objective_inventory")
    objective_ids = tuple(item.get("objective_id") for item in objectives)
    if (
        len(set(objective_ids)) != len(objective_ids)
        or any(item.get("applicability") != "applicable" for item in objectives)
    ):
        raise _fail("objective_manifest")
    material = tuple(
        item["objective_id"]
        for item in objectives
        if item.get("materiality") == "material_required"
    )
    if not material:
        raise _fail("material_objective_set")
    actual = _verify_common(
        artifact,
        policy_id="retrieval_objective_support_policy_v1",
        expected_hash=(
            OBJECTIVE_SUPPORT_POLICY_HASH if Path(path) == _OBJECTIVE_SUPPORT_PATH else None
        ),
    )
    return ObjectiveSupportContract(
        policy_id=artifact["artifact_id"],
        policy_version=artifact["artifact_version"],
        policy_hash=actual,
        objective_count=len(objectives),
        material_objective_ids=material,
    )


def _verify_evidence_extractor(path: str | Path) -> EvidenceExtractorContract:
    artifact = _load(path)
    candidate = artifact.get("evidence_candidate", {})
    if (
        candidate.get(
            "exact_excerpt_must_be_nonempty_contiguous_substring_of_decoded_body"
        )
        is not True
        or candidate.get("provider_search_snippet_allowed") is not False
        or candidate.get("provider_citation_allowed") is not False
        or candidate.get("normalization_before_substring_match") != "none"
    ):
        raise _fail("evidence_extractor_contract")
    actual = _verify_common(
        artifact,
        policy_id="deterministic_trace_backed_evidence_extractor_and_matcher_v1",
        expected_hash=(
            EVIDENCE_EXTRACTOR_POLICY_HASH if Path(path) == _EVIDENCE_EXTRACTOR_PATH else None
        ),
    )
    return EvidenceExtractorContract(
        policy_id=artifact["artifact_id"],
        policy_version=artifact["artifact_version"],
        policy_hash=actual,
        trace_backed_only=True,
    )


def verify_ps1_contracts(
    *,
    source_classification_path: str | Path = _SOURCE_CLASSIFICATION_PATH,
    origin_registry_path: str | Path = _ORIGIN_REGISTRY_PATH,
    objective_support_path: str | Path = _OBJECTIVE_SUPPORT_PATH,
    evidence_extractor_path: str | Path = _EVIDENCE_EXTRACTOR_PATH,
) -> Ps1Contracts:
    """Verify all four frozen PS1 policy identities and closed inventories."""
    return Ps1Contracts(
        source_classification=_verify_source_classification(
            source_classification_path
        ),
        origin_registry=_verify_origin_registry(origin_registry_path),
        objective_support=_verify_objective_support(objective_support_path),
        evidence_extractor=_verify_evidence_extractor(evidence_extractor_path),
    )


@dataclass(frozen=True, slots=True, repr=False)
class Ps1DiscoveryUrl:
    candidate_id: str
    provider: str
    discovery_ordinal: int
    exact_url: str
    provider_snippet: str | None
    provider_citation: str | None
    canonical_evidence_eligible: bool = False
    _token: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _DISCOVERY_TOKEN:
            raise _fail("discovery_factory_required")


def record_ps1_discovery_url(
    *,
    candidate_id: Any,
    provider: Any,
    discovery_ordinal: Any,
    exact_url: Any,
    provider_snippet: Any = None,
    provider_citation: Any = None,
) -> Ps1DiscoveryUrl:
    """Record an untrusted discovery URL without promoting it to evidence."""
    if (
        type(candidate_id) is not str
        or not candidate_id
        or type(provider) is not str
        or not provider
        or type(discovery_ordinal) is not int
        or discovery_ordinal < 1
        or type(exact_url) is not str
        or not exact_url
        or provider_snippet is not None
        and type(provider_snippet) is not str
        or provider_citation is not None
        and type(provider_citation) is not str
    ):
        raise _fail("discovery_record")
    return Ps1DiscoveryUrl(
        candidate_id=candidate_id,
        provider=provider,
        discovery_ordinal=discovery_ordinal,
        exact_url=exact_url,
        provider_snippet=provider_snippet,
        provider_citation=provider_citation,
        _token=_DISCOVERY_TOKEN,
    )


def _origin_entries() -> tuple[dict[str, Any], ...]:
    verify_ps1_contracts()
    artifact = _load(_ORIGIN_REGISTRY_PATH)
    return tuple(_json_copy(item) for item in artifact["registry_entries"])


def _resolve_origin_rule(exact_url: str) -> tuple[dict[str, Any], str | None]:
    matches: list[tuple[dict[str, Any], str]] = []
    for entry in _origin_entries():
        reference = "rtr-registry-probe"
        member = {
            "position": 0,
            "url_role": "final_url",
            "exact_url": exact_url,
            "retrieval_auth_context": "public_unauthenticated",
            "origin_rule": entry["origin_rule"],
            "restricted_trace_reference": reference,
        }
        result = validate_url_security(
            exact_url=exact_url,
            url_role="final_url",
            retrieval_auth_context="public_unauthenticated",
            redirect_context={
                "capture_status": "no_redirect",
                "current_position": 0,
                "requested_position": 0,
                "final_position": 0,
                "members": [member],
            },
            origin_rule=entry["origin_rule"],
            restricted_trace_reference=reference,
        )
        if result["classification"] == "public_safe":
            matches.append((entry["origin_rule"], entry["registry_entry_id"]))
    if len(matches) == 1:
        return _json_copy(matches[0][0]), matches[0][1]
    return ({"status": "ambiguous" if matches else "missing"}, None)


def build_ps1_classifier_input(
    *,
    exact_urls: Sequence[Any],
    retrieval_auth_contexts: Sequence[Any],
    reference_capabilities: Mapping[int, RestrictedTraceReference],
) -> dict[str, Any]:
    """Build one complete frozen classifier input from captured trace members."""
    if (
        isinstance(exact_urls, (str, bytes, bytearray))
        or type(exact_urls) not in {tuple, list}
        or isinstance(retrieval_auth_contexts, (str, bytes, bytearray))
        or type(retrieval_auth_contexts) not in {tuple, list}
    ):
        raise _fail("refetch_trace_shape")
    urls = tuple(exact_urls)
    auth = tuple(retrieval_auth_contexts)
    if not urls or len(urls) != len(auth) or set(reference_capabilities) != set(
        range(len(urls))
    ):
        raise _fail("refetch_trace_shape")
    members: list[dict[str, Any]] = []
    for position, (url, context) in enumerate(zip(urls, auth, strict=True)):
        capability = reference_capabilities[position]
        if (
            type(url) is not str
            or type(context) is not str
            or not isinstance(capability, RestrictedTraceReference)
        ):
            raise _fail("refetch_trace_shape")
        if position == 0 and len(urls) > 1:
            role = "requested_url"
        elif position == len(urls) - 1:
            role = "final_url"
        else:
            role = "intermediate_redirect_url"
        rule, _ = _resolve_origin_rule(url)
        members.append(
            {
                "position": position,
                "url_role": role,
                "exact_url": url,
                "retrieval_auth_context": context,
                "origin_rule": rule,
                "restricted_trace_reference": capability.value,
            }
        )
    final = members[-1]
    return {
        "exact_url": final["exact_url"],
        "url_role": final["url_role"],
        "retrieval_auth_context": final["retrieval_auth_context"],
        "redirect_context": {
            "capture_status": "no_redirect" if len(members) == 1 else "complete",
            "current_position": len(members) - 1,
            "requested_position": 0,
            "final_position": len(members) - 1,
            "members": members,
        },
        "origin_rule": final["origin_rule"],
        "restricted_trace_reference": final["restricted_trace_reference"],
    }


@dataclass(frozen=True, slots=True)
class Ps1EvidenceCandidate:
    evidence_type: str
    exact_excerpt: str


@dataclass(frozen=True, slots=True, repr=False)
class Ps1RefetchObservation:
    discovery: Ps1DiscoveryUrl
    retrieval_attempt_ordinal: int
    tool_call_ordinal: int
    result_ordinal: int
    classifier_input: Mapping[str, Any] = field(repr=False)
    reference_capabilities: Mapping[int, RestrictedTraceReference] = field(
        repr=False
    )
    status_code: int
    captured_at: datetime
    display_name: str
    decoded_body: str = field(repr=False)
    evidence_candidates: tuple[Ps1EvidenceCandidate, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class Ps1AssemblyResult:
    _canonical_bundle_json: bytes = field(repr=False)
    canonical_evidence_bundle_hash: str
    _objective_support_json: bytes = field(repr=False)
    restricted_traces: tuple[RestrictedUrlTrace, ...] = field(
        repr=False,
        compare=False,
    )
    trace_inventory: ValidatedTracePositionInventory = field(
        repr=False,
        compare=False,
    )
    allocation_plan: RetrievalAllocationPlan = field(
        repr=False,
        compare=False,
    )
    _token: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _ASSEMBLY_TOKEN:
            raise _fail("assembly_factory_required")
        try:
            normalized = normalize_semantic_json(self._canonical_bundle_json)
            validated = CanonicalOutputSchemaRegistry.from_path(
                _OUTPUT_SCHEMA_PATH
            ).validate("retrieval_evidence_bundle_v1", normalized)
            bundle = json.loads(self._canonical_bundle_json.decode("utf-8"))
            support = json.loads(self._objective_support_json.decode("utf-8"))
        except (
            AttributeError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            ValueError,
        ) as exc:
            raise _fail("assembly_identity") from exc
        if (
            type(bundle) is not dict
            or type(support) is not list
            or validated.canonical_semantic_json.canonical_bytes
            != self._canonical_bundle_json
            or hashlib.sha256(self._canonical_bundle_json).hexdigest()
            != self.canonical_evidence_bundle_hash
            or tuple(support) != _objective_support(bundle)
            or not isinstance(self.trace_inventory, ValidatedTracePositionInventory)
            or not isinstance(self.allocation_plan, RetrievalAllocationPlan)
            or type(self.restricted_traces) is not tuple
            or any(
                not isinstance(item, RestrictedUrlTrace)
                for item in self.restricted_traces
            )
        ):
            raise _fail("assembly_identity")
        allocated_sources = {
            item.source_id: (item.safe_canonical_url, item.retrieved_at)
            for item in self.allocation_plan.sources
        }
        bundled_sources = {
            item.get("source_id"): (item.get("url"), item.get("retrieved_at"))
            for item in bundle.get("sources", ())
            if type(item) is dict
        }
        allocated_evidence = {
            item.evidence_id: item.source_id for item in self.allocation_plan.evidence
        }
        bundled_evidence = {
            evidence.get("evidence_id"): source.get("source_id")
            for source in bundle.get("sources", ())
            if type(source) is dict
            for evidence in source.get("evidence_items", ())
            if type(evidence) is dict
        }
        if (
            bundled_sources != allocated_sources
            or bundled_evidence != allocated_evidence
            or len(self.restricted_traces) != len(self.trace_inventory.source_positions)
        ):
            raise _fail("assembly_allocation_binding")

    @property
    def canonical_bundle(self) -> dict[str, Any]:
        return json.loads(self._canonical_bundle_json.decode("utf-8"))

    @property
    def objective_support(self) -> tuple[dict[str, str], ...]:
        return tuple(json.loads(self._objective_support_json.decode("utf-8")))

    def ordinary_projection(self) -> dict[str, Any]:
        return _json_copy(
            {
                "canonical_bundle": self.canonical_bundle,
                "canonical_evidence_bundle_hash": self.canonical_evidence_bundle_hash,
                "objective_support": list(self.objective_support),
                "source_classification_policy": {
                    "policy_id": "source_classification_policy_v1",
                    "policy_version": "v1",
                    "policy_hash": SOURCE_CLASSIFICATION_POLICY_HASH,
                },
                "origin_registry": {
                    "policy_id": "url_security_operational_origin_rule_registry_v1",
                    "policy_version": "v1",
                    "policy_hash": ORIGIN_RULE_REGISTRY_HASH,
                },
                "objective_support_policy": {
                    "policy_id": "retrieval_objective_support_policy_v1",
                    "policy_version": "v1",
                    "policy_hash": OBJECTIVE_SUPPORT_POLICY_HASH,
                },
                "evidence_extractor_policy": {
                    "policy_id": (
                        "deterministic_trace_backed_evidence_extractor_and_matcher_v1"
                    ),
                    "policy_version": "v1",
                    "policy_hash": EVIDENCE_EXTRACTOR_POLICY_HASH,
                },
            }
        )


def _require_refetch_shape(item: Any) -> Ps1RefetchObservation:
    if (
        not isinstance(item, Ps1RefetchObservation)
        or not isinstance(item.discovery, Ps1DiscoveryUrl)
        or item.discovery._token is not _DISCOVERY_TOKEN
        or type(item.retrieval_attempt_ordinal) is not int
        or item.retrieval_attempt_ordinal < 1
        or type(item.tool_call_ordinal) is not int
        or item.tool_call_ordinal < 1
        or type(item.result_ordinal) is not int
        or item.result_ordinal < 1
        or type(item.status_code) is not int
        or not isinstance(item.captured_at, datetime)
        or item.captured_at.tzinfo is None
        or item.captured_at.utcoffset() != UTC.utcoffset(item.captured_at)
        or type(item.display_name) is not str
        or not item.display_name
        or type(item.decoded_body) is not str
        or type(item.evidence_candidates) is not tuple
        or not item.evidence_candidates
    ):
        raise _fail("refetch_observation")
    return item


def _evidence_type_coherent(candidate: Ps1EvidenceCandidate) -> bool:
    if (
        not isinstance(candidate, Ps1EvidenceCandidate)
        or candidate.evidence_type not in _EVIDENCE_TYPES
        or type(candidate.exact_excerpt) is not str
        or not candidate.exact_excerpt
    ):
        return False
    content = candidate.exact_excerpt
    if candidate.evidence_type == "identity":
        return "MX Master 3S" in content
    if candidate.evidence_type == "price":
        return _PRICE.search(content) is not None
    if candidate.evidence_type == "availability":
        return any(
            marker in content
            for marker in ("Available", "In stock", "Unavailable", "no longer available")
        )
    if candidate.evidence_type == "bundle":
        return "Logi Bolt" in content and "receiver" in content
    if candidate.evidence_type == "regional_context":
        return "United States" in content or "USD" in content
    return False


def _source_type_for_rule_id(rule_id: str) -> str:
    entries = tuple(
        entry
        for entry in _origin_entries()
        if entry["registry_entry_id"] == rule_id
    )
    if len(entries) != 1 or entries[0]["source_type"] not in _SUPPORTED_SOURCE_TYPES:
        raise _fail("source_classification")
    return entries[0]["source_type"]


def _objective_support(bundle: dict[str, Any]) -> tuple[dict[str, str], ...]:
    sources = bundle["sources"]

    def source_evidence(source_type: str) -> tuple[dict[str, Any], ...]:
        return tuple(source for source in sources if source["source_type"] == source_type)

    def excerpts(source: dict[str, Any], evidence_type: str) -> tuple[str, ...]:
        return tuple(
            item["content"]
            for item in source["evidence_items"]
            if item["evidence_type"] == evidence_type
        )

    def conflicting(source: dict[str, Any]) -> bool:
        return any(
            marker in content
            for content in excerpts(source, "identity")
            for marker in _CONFLICT_MARKERS
        )

    manufacturer = source_evidence("manufacturer")
    retailer = source_evidence("established_retailer")

    identity_support = "insufficient"
    for source in manufacturer:
        if conflicting(source):
            identity_support = "conflicting"
            break
        identity_ok = any(
            all(marker in content for marker in ("MX Master 3S", "Graphite", "right-handed"))
            for content in excerpts(source, "identity")
        )
        bundle_ok = any(
            "Logi Bolt" in content and "receiver" in content
            for content in excerpts(source, "bundle")
        )
        if identity_ok and bundle_ok:
            identity_support = "sufficient"
            break

    offer_support = "insufficient"
    for source in retailer:
        if conflicting(source):
            offer_support = "conflicting"
            break
        identity_ok = any(
            "MX Master 3S" in content and "910-006556" in content
            for content in excerpts(source, "identity")
        )
        price_ok = any(_PRICE.search(content) for content in excerpts(source, "price"))
        availability_ok = bool(excerpts(source, "availability"))
        region_ok = any(
            "United States" in content and "USD" in content
            for content in excerpts(source, "regional_context")
        )
        if identity_ok and price_ok and availability_ok and region_ok:
            offer_support = "sufficient"
            break

    distinction_support = (
        "sufficient"
        if any(excerpts(source, "price") for source in manufacturer)
        and any(excerpts(source, "price") for source in retailer)
        else "insufficient"
    )
    return (
        {"objective_id": "ps1_exact_product_variant", "support": identity_support},
        {"objective_id": "ps1_current_us_retail_offer", "support": offer_support},
        {
            "objective_id": "ps1_manufacturer_retailer_distinction",
            "support": distinction_support,
        },
    )


def assemble_ps1_evidence_bundle(
    *,
    retrieval_status: Any,
    discoveries: Sequence[Any],
    refetch_observations: Sequence[Any],
) -> Ps1AssemblyResult:
    """Construct and validate one canonical PS1 bundle from local refetch inputs."""
    contracts = verify_ps1_contracts()
    if isinstance(discoveries, (str, bytes, bytearray)) or type(discoveries) not in {
        tuple,
        list,
    }:
        raise _fail("discovery_inventory")
    discovery_items = tuple(discoveries)
    if not discovery_items or any(
        not isinstance(item, Ps1DiscoveryUrl) or item._token is not _DISCOVERY_TOKEN
        for item in discovery_items
    ):
        raise _fail("discovery_inventory")
    if isinstance(refetch_observations, (str, bytes, bytearray)) or type(
        refetch_observations
    ) not in {tuple, list}:
        raise _fail("refetch_inventory")
    refetches = tuple(_require_refetch_shape(item) for item in refetch_observations)
    if not refetches:
        raise _fail("trace_backed_refetch_required")

    discovered_urls = {item.exact_url for item in discovery_items}
    trace_inventory_inputs: dict[str, Any] = {
        "retrieval_attempt_ordinals": [],
        "tool_call_ordinals_by_attempt": {},
        "result_ordinals_by_tool_call": {},
        "evidence_ordinals_by_result": {},
    }
    source_observations: list[RetrievalSourceObservation] = []
    evidence_observations: list[RetrievalEvidenceObservation] = []
    candidates_by_position: dict[tuple[int, int, int, int], Ps1EvidenceCandidate] = {}
    source_type_by_key: dict[str, str] = {}
    restricted_traces: list[RestrictedUrlTrace] = []

    attempts = sorted({item.retrieval_attempt_ordinal for item in refetches})
    trace_inventory_inputs["retrieval_attempt_ordinals"] = attempts
    for attempt in attempts:
        tools = sorted(
            {
                item.tool_call_ordinal
                for item in refetches
                if item.retrieval_attempt_ordinal == attempt
            }
        )
        trace_inventory_inputs["tool_call_ordinals_by_attempt"][attempt] = tools
        for tool in tools:
            results = sorted(
                item.result_ordinal
                for item in refetches
                if item.retrieval_attempt_ordinal == attempt
                and item.tool_call_ordinal == tool
            )
            trace_inventory_inputs["result_ordinals_by_tool_call"][(attempt, tool)] = results

    for item in sorted(
        refetches,
        key=lambda value: (
            value.retrieval_attempt_ordinal,
            value.tool_call_ordinal,
            value.result_ordinal,
        ),
    ):
        position = (
            item.retrieval_attempt_ordinal,
            item.tool_call_ordinal,
            item.result_ordinal,
        )
        evidence_ordinals = list(range(1, len(item.evidence_candidates) + 1))
        trace_inventory_inputs["evidence_ordinals_by_result"][position] = evidence_ordinals
        requested_position = item.classifier_input.get("redirect_context", {}).get(
            "requested_position"
        )
        members = item.classifier_input.get("redirect_context", {}).get("members")
        if (
            type(requested_position) is not int
            or type(members) is not list
            or requested_position < 0
            or requested_position >= len(members)
            or members[requested_position].get("exact_url") not in discovered_urls
        ):
            raise _fail("discovery_refetch_linkage")
        if item.status_code != 200:
            raise _fail("refetch_transport_status")
        try:
            trace = capture_restricted_url_trace(
                dict(item.classifier_input),
                reference_capabilities=dict(item.reference_capabilities),
            )
        except (TypeError, ValueError) as exc:
            raise _fail("url_security_trace") from exc
        safe = trace.as_safe_result_dict()
        if safe["classification"] != "public_safe":
            reason = safe["reason_codes"][0] if safe["reason_codes"] else "indeterminate"
            raise _fail(f"url_security:{reason}")
        try:
            deduplication_key = derive_public_safe_deduplication_key(
                **dict(item.classifier_input)
            )
        except (TypeError, ValueError) as exc:
            raise _fail("url_security") from exc
        final_rule = item.classifier_input.get("origin_rule")
        if type(final_rule) is not dict or type(final_rule.get("rule_id")) is not str:
            raise _fail("source_classification")
        source_type = _source_type_for_rule_id(final_rule["rule_id"])
        source_type_by_key[deduplication_key.value] = source_type
        try:
            body_bytes = item.decoded_body.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise _fail("refetch_body") from exc
        if len(body_bytes) > RESOURCE_LIMIT_VALUES["maximum_raw_response_bytes"]:
            raise _fail("resource_limit")
        source_observations.append(
            RetrievalSourceObservation(
                retrieval_attempt_ordinal=position[0],
                tool_call_ordinal=position[1],
                result_ordinal=position[2],
                successful=True,
                deduplication_key=deduplication_key,
                name=item.display_name,
                captured_at=item.captured_at,
            )
        )
        for evidence_ordinal, candidate in enumerate(item.evidence_candidates, start=1):
            evidence_position = (*position, evidence_ordinal)
            if (
                not isinstance(candidate, Ps1EvidenceCandidate)
                or type(candidate.exact_excerpt) is not str
                or not candidate.exact_excerpt
                or candidate.exact_excerpt not in item.decoded_body
            ):
                raise _fail("trace_backed_excerpt")
            if (
                not _evidence_type_coherent(candidate)
                or len(candidate.exact_excerpt.encode("utf-8")) > 12_000
            ):
                raise _fail("evidence_type_coherence")
            candidates_by_position[evidence_position] = candidate
            evidence_observations.append(
                RetrievalEvidenceObservation(
                    retrieval_attempt_ordinal=position[0],
                    tool_call_ordinal=position[1],
                    result_ordinal=position[2],
                    evidence_observation_ordinal=evidence_ordinal,
                    successful=True,
                    source_deduplication_key=deduplication_key,
                )
            )
        restricted_traces.append(trace)

    try:
        inventory = validate_trace_position_inventory(**trace_inventory_inputs)
        allocation = allocate_retrieval_observations(
            inventory,
            source_observations,
            evidence_observations,
        )
    except (TypeError, ValueError) as exc:
        raise _fail(f"trace_allocation:{exc}") from exc

    source_by_id: dict[str, dict[str, Any]] = {}
    for source in allocation.sources:
        source_by_id[source.source_id] = {
            "source_id": source.source_id,
            "name": source.display_name,
            "url": source.safe_canonical_url,
            "source_type": source_type_by_key[source.deduplication_url_key],
            "retrieved_at": source.retrieved_at,
            "evidence_items": [],
        }
    for evidence in allocation.evidence:
        candidate = candidates_by_position[evidence.observation_key]
        source_by_id[evidence.source_id]["evidence_items"].append(
            {
                "evidence_id": evidence.evidence_id,
                "evidence_type": candidate.evidence_type,
                "content": candidate.exact_excerpt,
            }
        )
    bundle = {
        "retrieval_status": retrieval_status,
        "sources": [source_by_id[source.source_id] for source in allocation.sources],
    }
    try:
        canonical = normalize_semantic_json(_canonical_bytes(bundle))
        registry = CanonicalOutputSchemaRegistry.from_path(_OUTPUT_SCHEMA_PATH)
        validated = registry.validate("retrieval_evidence_bundle_v1", canonical)
    except (TypeError, ValueError) as exc:
        raise _fail("canonical_schema") from exc
    support = _objective_support(bundle)
    material_support = tuple(item["support"] for item in support[:2])
    try:
        validate_retrieval_status_coherence(
            retrieval_status,
            material_support,
            len(bundle["sources"]),
        )
    except ValueError as exc:
        raise _fail("retrieval_status_coherence") from exc
    canonical_hash = validated.canonical_semantic_json.strict_parsed_semantic_payload_hash
    if not contracts.provider_calls_allowed and canonical_hash != hashlib.sha256(
        validated.canonical_semantic_json.canonical_bytes
    ).hexdigest():
        raise _fail("bundle_identity")
    return Ps1AssemblyResult(
        _canonical_bundle_json=validated.canonical_semantic_json.canonical_bytes,
        canonical_evidence_bundle_hash=canonical_hash,
        _objective_support_json=_canonical_bytes(list(support)),
        restricted_traces=tuple(restricted_traces),
        trace_inventory=inventory,
        allocation_plan=allocation,
        _token=_ASSEMBLY_TOKEN,
    )
