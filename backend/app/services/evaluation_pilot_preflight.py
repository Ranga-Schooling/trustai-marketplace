"""Provider-free aggregation of the current pilot-preflight checkpoint.

The assessment verifies existing frozen artifacts and reports remaining
boundaries.  It cannot authorize execution, inspect credentials, or perform a
network/provider operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.evaluation_contract_identity import (
    load_strict_contract_json,
    verify_normalization_parser_artifact,
    verify_output_schema_artifact,
    verify_prompt_template_artifact,
)
from app.services.evaluation_data_handling import verify_provider_data_handling_artifact
from app.services.evaluation_pilot_visual_assets import verify_pilot_visual_assets
from app.services.evaluation_pricing import verify_pricing_snapshot
from app.services.evaluation_ps1 import verify_ps1_contracts
from app.services.evaluation_provider_adapters import bind_provider_adapters
from app.services.evaluation_provider_role_mappings import bind_provider_role_mappings
from app.services.evaluation_request_configurations import bind_pilot_request_configurations
from app.services.evaluation_region_binding import verify_pilot_region_binding
from app.services.evaluation_resource_limits import assess_resource_limit_policy
from app.services.evaluation_result_record import verify_result_record_contract
from app.services.evaluation_retry_policy import load_retry_policy
from app.services.evaluation_search_authority import bind_search_authority_v2
from app.services.evaluation_search_tool_record import verify_safe_search_tool_record_contract
from app.services.evaluation_visual_context import bind_visual_context_contract


_ROOT = Path(__file__).resolve().parents[3]
_ARTIFACTS = _ROOT / "docs" / "testing" / "ai-evaluation"
REQUEST_CONFIGURATION_HASH = (
    "1aaca1df3d67f51c3d9c1e5638d63b541bd947a1301aa509291cc7445e60b152"
)
_VISUAL_CONTEXT_HASH = (
    "7e6c51a9484f7e9de6910caa829728298b5e4d787af52106e9e2797ddbcae961"
)
_ELIGIBLE_STAGE_MATRIX = (
    ("openai_unified_premium_v1", "text_analysis", 2),
    ("openai_unified_premium_v1", "search_retrieval", 1),
    ("openai_unified_premium_v1", "search_synthesis", 1),
    ("openai_unified_premium_v1", "visual_inspection", 2),
    ("openai_unified_balanced_v1", "text_analysis", 2),
    ("openai_unified_balanced_v1", "search_retrieval", 1),
    ("openai_unified_balanced_v1", "search_synthesis", 1),
    ("openai_unified_balanced_v1", "visual_inspection", 2),
    ("gemini_unified_v1", "text_analysis", 2),
    ("gemini_unified_v1", "search_retrieval", 1),
    ("gemini_unified_v1", "search_synthesis", 1),
    ("gemini_unified_v1", "visual_inspection", 2),
    ("groq_split_v1", "text_analysis", 2),
    ("groq_split_v1", "search_retrieval", 1),
    ("groq_split_v1", "search_synthesis", 1),
    ("groq_split_v1", "visual_inspection", 2),
    ("baseline_current_text_v1", "text_analysis", 2),
)
_INELIGIBLE_RETRIEVAL: tuple[tuple[str, str], ...] = ()
_RESOLVED_COMPONENTS = (
    "frozen_methodology_and_fixtures",
    "prompt_and_output_contracts",
    "normalization_and_validation",
    "resource_limits",
    "retry_policy",
    "privacy_and_restricted_trace_handling",
    "provider_role_mappings_and_response_adapters",
    "pilot_request_configurations",
    "pilot_visual_assets_truth_and_context",
    "immutable_result_record_with_request_configuration_binding",
    "dated_official_pricing_schedules",
    "ps1_discovery_refetch_classification_extraction_and_support",
    "approved_us_operation_and_restricted_local_storage_binding",
)
_DECISION_PACKAGES = (
    "pilot_budget_ceiling",
    "credential_authorization_handling_and_scope",
    "explicit_pilot_authorization",
)
_PS1_BLOCKERS: tuple[str, ...] = ()
_PS1_REUSE = (
    "bounded_ssrf_safe_fetch_transport",
    "strict_url_security_and_redirect_auth_classification",
    "deterministic_retrieval_ordinals_source_ids_and_evidence_ids",
    "restricted_exact_trace_and_safe_ordinary_projection",
    "safe_search_tool_result_record",
)


class PilotPreflightError(ValueError):
    """A required frozen identity or provider-free prerequisite is stale."""


@dataclass(frozen=True, slots=True)
class ProviderNeutralPilotPreflight:
    status: str
    resolved_components: tuple[str, ...]
    remaining_decision_packages: tuple[str, ...]
    eligible_stage_matrix: tuple[tuple[str, str, int], ...]
    ineligible_stage_matrix: tuple[tuple[str, str], ...]
    ps1_provider_free_blockers: tuple[str, ...]
    ps1_reusable_primitives: tuple[str, ...]
    provider_calls_in_currently_configured_non_search_scope: int
    planned_provider_calls_after_ps1_resolution: int
    maximum_physical_attempts_after_ps1_resolution: int
    same_day_lifecycle_recheck_required: bool = True
    ps1_built_in_search_evidence_eligible: bool = False
    ps1_trace_backed_application_evidence_ready: bool = True
    ps1_security_contract_weakened: bool = False
    operation_country_code: str = "US"
    provider_service_mode: str = "standard_global"
    restricted_storage_country_code: str = "US"
    cross_region_replication_allowed: bool = False
    provider_calls_allowed: bool = False
    pilot_calls_allowed: bool = False
    scored_calls_allowed: bool = False
    provider_calls_completed: int = 0
    pilot_calls_completed: int = 0
    scored_calls_completed: int = 0
    winner_selected: bool = False
    independently_authorizes_execution: bool = False


def _load(name: str):
    return load_strict_contract_json(_ARTIFACTS / name)


def assess_provider_neutral_pilot_preflight() -> ProviderNeutralPilotPreflight:
    """Verify all currently resolved provider-free pilot inputs."""
    parser = _load("normalization-parser.v1.json")
    prompts = _load("prompt-templates.v1.json")
    schemas = _load("output-schemas.v1.json")
    verify_normalization_parser_artifact(parser)
    verify_prompt_template_artifact(prompts)
    verify_output_schema_artifact(schemas)
    resource = assess_resource_limit_policy(parser["resource_limit_policy"])
    if not resource.ready:
        raise PilotPreflightError("resource_limits")

    authority = bind_search_authority_v2(
        _load("search-authority.v2.json"), prompts, parser
    )
    mappings = bind_provider_role_mappings(
        _load("provider-role-mappings.v1.json"), authority
    )
    adapters = bind_provider_adapters(_load("provider-adapters.v1.json"), mappings)
    configurations = bind_pilot_request_configurations(
        _load("request-configurations.v1.json"), mappings, adapters
    )
    if configurations.semantic_hash != REQUEST_CONFIGURATION_HASH:
        raise PilotPreflightError("request_configuration_identity")

    visual = bind_visual_context_contract(
        _load("visual-context.v1.json"),
        _load("pilot-fixtures.v1.json"),
        prompts,
    )
    if visual.semantic_hash != _VISUAL_CONTEXT_HASH:
        raise PilotPreflightError("visual_context_identity")
    verify_pilot_visual_assets(_ARTIFACTS / "visual-asset-and-truth-records.v1.json")
    load_retry_policy(_ARTIFACTS / "retry-policy.v1.json")
    verify_provider_data_handling_artifact(
        _ARTIFACTS / "provider-data-handling-review.v1.json"
    )
    verify_safe_search_tool_record_contract(
        _ARTIFACTS / "safe-search-tool-record.v1.json"
    )
    verify_result_record_contract(_ARTIFACTS / "result-record.v1.json")
    ps1 = verify_ps1_contracts()
    if ps1.provider_calls_allowed:
        raise PilotPreflightError("ps1_execution_boundary")
    region = verify_pilot_region_binding()
    pricing = verify_pricing_snapshot(_ARTIFACTS / "pricing-snapshot.v1.json")
    if pricing.observed_on != "2026-08-31":
        raise PilotPreflightError("pricing_observation_date")

    non_search = sum(
        fixture_count
        for _, stage, fixture_count in _ELIGIBLE_STAGE_MATRIX
        if stage not in {"search_retrieval", "search_synthesis"}
    )
    search = sum(
        fixture_count
        for _, stage, fixture_count in _ELIGIBLE_STAGE_MATRIX
        if stage in {"search_retrieval", "search_synthesis"}
    )
    planned = non_search + search
    return ProviderNeutralPilotPreflight(
        status="provider_neutral_ready_awaiting_budget_credentials_and_authorization",
        resolved_components=_RESOLVED_COMPONENTS,
        remaining_decision_packages=_DECISION_PACKAGES,
        eligible_stage_matrix=_ELIGIBLE_STAGE_MATRIX,
        ineligible_stage_matrix=_INELIGIBLE_RETRIEVAL,
        ps1_provider_free_blockers=_PS1_BLOCKERS,
        ps1_reusable_primitives=_PS1_REUSE,
        provider_calls_in_currently_configured_non_search_scope=non_search,
        planned_provider_calls_after_ps1_resolution=planned,
        maximum_physical_attempts_after_ps1_resolution=planned * 2,
        operation_country_code=region.operation_country_code,
        provider_service_mode=region.provider_service_mode,
        restricted_storage_country_code=region.restricted_storage_country_code,
        cross_region_replication_allowed=region.cross_region_replication_allowed,
    )
