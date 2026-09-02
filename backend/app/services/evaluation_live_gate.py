"""Hash-bound same-day certification and external human pilot authorization.

This module validates records.  It cannot create an approved authorization,
read credentials, configure a provider account, or invoke a provider.
"""

from __future__ import annotations

from collections.abc import Mapping
import copy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from app.services.evaluation_contract_identity import load_strict_contract_json
from app.services.evaluation_pilot_runner import (
    CREDENTIAL_VARIABLE_BY_PROVIDER,
    CredentialReference,
    LiveGateBinding,
    ProviderFreePilotRunner,
)


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_UTC_SECONDS = re.compile(
    r"(?:19|20)[0-9]{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])T"
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z\Z"
)
_GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
_AUTHORIZATION_FIELDS = {
    "authorization_id",
    "authorization_version",
    "status",
    "evaluation_id",
    "experiment_phase",
    "repository_head",
    "scope",
    "authorized_call_ids",
    "budget_control_hash",
    "region_binding_hash",
    "same_day_certification_hash",
    "credential_readiness",
    "provider_control_confirmation",
    "authorized_at_utc",
    "scored_execution_authorized",
    "production_deployment_authorized",
    "semantic_hash",
}


class LiveBoundaryGateError(ValueError):
    """A certification or human authorization failed closed."""


def _fail(code: str) -> LiveBoundaryGateError:
    return LiveBoundaryGateError(code)


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise _fail("canonicalization") from exc


def _hash_detached(document: Mapping[str, Any], *, path: tuple[str, ...]) -> str:
    detached = copy.deepcopy(dict(document))
    target = detached
    try:
        for segment in path[:-1]:
            target = target[segment]
        target[path[-1]] = None
    except (KeyError, TypeError) as exc:
        raise _fail("identity") from exc
    return hashlib.sha256(_canonical(detached)).hexdigest()


@dataclass(frozen=True, slots=True)
class SameDayCertification:
    artifact_id: str
    artifact_version: str
    semantic_hash: str
    observation_date: str
    observed_at_utc: str
    repository_head_reviewed: str
    request_configuration_set_hash: str
    budget_control_hash: str
    region_binding_hash: str
    pricing_snapshot_hash: str
    documentation_compatible_call_ids: tuple[str, ...]
    pricing_unchanged: bool
    provider_calls_completed: int = 0
    independently_authorizes_execution: bool = False


@dataclass(frozen=True, slots=True)
class ValidatedPilotAuthorization:
    semantic_hash: str
    scope: str
    authorized_call_ids: tuple[str, ...]
    credential_readiness: tuple[tuple[str, str], ...]
    provider_control_confirmation: tuple[tuple[str, str], ...]


def load_same_day_certification(
    path: str | Path,
    *,
    current_date: str,
) -> SameDayCertification:
    """Verify one immutable public-documentation certification record."""
    try:
        document = load_strict_contract_json(path)
    except (OSError, TypeError, ValueError) as exc:
        raise _fail("certification_json") from exc
    identity = document.get("specification_identity")
    execution = document.get("execution_boundary")
    bindings = document.get("frozen_bindings")
    freshness = document.get("freshness")
    pricing = document.get("pricing_recheck")
    stored_hash = identity.get("semantic_hash") if type(identity) is dict else None
    expected_calls = [f"call-{index:04d}" for index in range(1, 23)]
    if (
        document.get("artifact_id") != "live_provider_certification_2026_09_01"
        or document.get("artifact_version") != "v1"
        or document.get("status")
        != "documentation_verified_user_controls_credentials_and_authorization_pending"
        or document.get("observation_date") != "2026-09-01"
        or _UTC_SECONDS.fullmatch(document.get("observed_at_utc", "")) is None
        or type(identity) is not dict
        or type(stored_hash) is not str
        or _SHA256.fullmatch(stored_hash) is None
        or _hash_detached(document, path=("specification_identity", "semantic_hash"))
        != stored_hash
        or type(freshness) is not dict
        or freshness.get("valid_on_date_only") != document.get("observation_date")
        or freshness.get("time_zone_for_date_comparison") != "UTC"
        or type(bindings) is not dict
        or _GIT_SHA.fullmatch(bindings.get("repository_head_reviewed", "")) is None
        or any(
            _SHA256.fullmatch(bindings.get(field, "")) is None
            for field in (
                "request_configuration_set_hash",
                "budget_control_hash",
                "region_binding_hash",
                "pricing_snapshot_hash",
            )
        )
        or document.get("documentation_compatible_call_ids") != expected_calls
        or type(pricing) is not dict
        or pricing.get("pricing_unchanged") is not True
        or pricing.get("approved_ceiling_usd") != "5.00"
        or type(execution) is not dict
        or execution
        != {
            "provider_calls_allowed": False,
            "pilot_calls_allowed": False,
            "scored_calls_allowed": False,
            "provider_calls_completed": 0,
            "pilot_calls_completed": 0,
            "scored_calls_completed": 0,
            "winner_selected": False,
            "this_artifact_independently_authorizes_execution": False,
        }
    ):
        raise _fail("certification_contract")
    if current_date != document["observation_date"]:
        raise _fail("certification_freshness")
    providers = document.get("provider_certifications")
    if (
        type(providers) is not list
        or tuple(item.get("provider") for item in providers if type(item) is dict)
        != tuple(CREDENTIAL_VARIABLE_BY_PROVIDER)
        or any(type(item.get("blockers")) is not list or item["blockers"] for item in providers)
    ):
        raise _fail("certification_provider_inventory")
    return SameDayCertification(
        artifact_id=document["artifact_id"],
        artifact_version=document["artifact_version"],
        semantic_hash=stored_hash,
        observation_date=document["observation_date"],
        observed_at_utc=document["observed_at_utc"],
        repository_head_reviewed=bindings["repository_head_reviewed"],
        request_configuration_set_hash=bindings["request_configuration_set_hash"],
        budget_control_hash=bindings["budget_control_hash"],
        region_binding_hash=bindings["region_binding_hash"],
        pricing_snapshot_hash=bindings["pricing_snapshot_hash"],
        documentation_compatible_call_ids=tuple(expected_calls),
        pricing_unchanged=True,
    )


def authorization_semantic_hash(document: Mapping[str, Any]) -> str:
    return _hash_detached(document, path=("semantic_hash",))


def validate_pilot_authorization(
    document: Mapping[str, Any],
    *,
    runner: ProviderFreePilotRunner,
    certification: SameDayCertification,
) -> ValidatedPilotAuthorization:
    """Validate an externally created explicit human pilot authorization."""
    if type(document) is not dict or set(document) != _AUTHORIZATION_FIELDS:
        raise _fail("authorization_shape")
    stored_hash = document.get("semantic_hash")
    if (
        type(stored_hash) is not str
        or _SHA256.fullmatch(stored_hash) is None
        or authorization_semantic_hash(document) != stored_hash
    ):
        raise _fail("authorization_hash")
    scope = document.get("scope")
    calls = document.get("authorized_call_ids")
    all_calls = tuple(item.call_id for item in runner.plan.provider_calls)
    if (
        type(document.get("authorization_id")) is not str
        or not document["authorization_id"]
        or document.get("authorization_version") != "v1"
        or document.get("status") != "approved"
        or document.get("evaluation_id") != runner.evaluation_id
        or document.get("experiment_phase") != "pilot"
        or document.get("repository_head") != runner.repository_harness_commit_sha
        or document.get("budget_control_hash") != runner.budget_control_hash
        or document.get("region_binding_hash") != runner.region_binding_hash
        or document.get("same_day_certification_hash") != certification.semantic_hash
        or _UTC_SECONDS.fullmatch(document.get("authorized_at_utc", "")) is None
        or document["authorized_at_utc"][:10] != certification.observation_date
        or document["authorized_at_utc"] < certification.observed_at_utc
        or document.get("scored_execution_authorized") is not False
        or document.get("production_deployment_authorized") is not False
        or scope not in {"first_attempt_only", "full_authorized_pilot"}
        or type(calls) is not list
        or any(type(item) is not str for item in calls)
        or len(calls) != len(set(calls))
        or any(item not in certification.documentation_compatible_call_ids for item in calls)
        or (scope == "first_attempt_only" and len(calls) != 1)
        or (scope == "full_authorized_pilot" and tuple(calls) != all_calls)
    ):
        raise _fail("authorization_contract")
    credentials = document.get("credential_readiness")
    controls = document.get("provider_control_confirmation")
    if (
        type(credentials) is not dict
        or tuple(credentials) != tuple(CREDENTIAL_VARIABLE_BY_PROVIDER.values())
        or any(value not in {"PRESENT", "MISSING"} for value in credentials.values())
        or type(controls) is not dict
        or tuple(controls) != tuple(CREDENTIAL_VARIABLE_BY_PROVIDER)
        or any(value not in {"confirmed", "pending"} for value in controls.values())
    ):
        raise _fail("authorization_readiness")
    providers = {
        next(item.provider for item in runner.plan.provider_calls if item.call_id == call_id)
        for call_id in calls
    }
    for provider in providers:
        variable = CREDENTIAL_VARIABLE_BY_PROVIDER[provider]
        if credentials[variable] != "PRESENT" or controls[provider] != "confirmed":
            raise _fail("authorization_readiness")
    return ValidatedPilotAuthorization(
        semantic_hash=stored_hash,
        scope=scope,
        authorized_call_ids=tuple(calls),
        credential_readiness=tuple(credentials.items()),
        provider_control_confirmation=tuple(controls.items()),
    )


# A deliberately narrow helper for offline operator tooling and tests.
validate_pilot_authorization.compute_hash = authorization_semantic_hash  # type: ignore[attr-defined]


def build_live_gate_binding(
    *,
    runner: ProviderFreePilotRunner,
    certification: SameDayCertification,
    authorization_document: Mapping[str, Any],
    current_date: str,
) -> LiveGateBinding:
    """Bind validated external facts; never synthesize an approval."""
    if (
        not isinstance(runner, ProviderFreePilotRunner)
        or not isinstance(certification, SameDayCertification)
        or certification.observation_date != current_date
        or certification.request_configuration_set_hash
        != runner.request_configuration_set_hash
        or certification.budget_control_hash != runner.budget_control_hash
        or certification.region_binding_hash != runner.region_binding_hash
    ):
        raise _fail("live_binding_contract")
    authorization = validate_pilot_authorization(
        authorization_document,
        runner=runner,
        certification=certification,
    )
    readiness = dict(authorization.credential_readiness)
    references = tuple(
        CredentialReference(
            provider,
            variable,
            (
                "externally_confirmed_for_live_pilot"
                if readiness[variable] == "PRESENT"
                else "pending_external_presence_check"
            ),
        )
        for provider, variable in CREDENTIAL_VARIABLE_BY_PROVIDER.items()
    )
    return LiveGateBinding._verified_live(
        evaluation_id=runner.evaluation_id,
        experiment_version=runner.experiment_version,
        request_configuration_set_hash=runner.request_configuration_set_hash,
        budget_control_hash=runner.budget_control_hash,
        region_binding_hash=runner.region_binding_hash,
        valid_on_date=current_date,
        credential_references=references,
        repository_harness_commit_sha=runner.repository_harness_commit_sha,
        same_day_certification_hash=certification.semantic_hash,
        pilot_authorization_hash=authorization.semantic_hash,
        authorized_call_ids=authorization.authorized_call_ids,
        authorization_scope=authorization.scope,
    )
