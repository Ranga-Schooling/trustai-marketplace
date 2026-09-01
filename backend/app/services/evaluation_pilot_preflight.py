"""Provider-free aggregation of the current pilot-preflight checkpoint.

The assessment verifies existing frozen artifacts and reports remaining
boundaries.  It cannot authorize execution, inspect credentials, or perform a
network/provider operation.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

from app.services.evaluation_contract_identity import (
    load_strict_contract_json,
    verify_normalization_parser_artifact,
    verify_output_schema_artifact,
    verify_prompt_template_artifact,
)
from app.services.evaluation_data_handling import verify_provider_data_handling_artifact
from app.services.evaluation_pilot_visual_assets import verify_pilot_visual_assets
from app.services.evaluation_pilot_cost_envelope import verify_pilot_cost_envelope
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
COST_ENVELOPE_HASH = (
    "7223f8fad4774b8fe431d90475b5aebe53456a509af69bb54daefd1e10636398"
)
_VISUAL_CONTEXT_HASH = (
    "7e6c51a9484f7e9de6910caa829728298b5e4d787af52106e9e2797ddbcae961"
)
_EXPERIMENT_FILE_SHA256 = (
    "157615e8aea8565389b11f1c041a2a3a5013a4e740887bb60cc70563114e9e79"
)
_PILOT_FIXTURE_FILE_SHA256 = (
    "95a6670975becfdecd39f091c6760652c237ad4c449c9fdb8b7e68d93010cfb9"
)
_CONFIGURED_STAGE_MATRIX = (
    ("openai_unified_premium_v1", "text_analysis", 2),
    ("openai_unified_premium_v1", "search_synthesis", 1),
    ("openai_unified_premium_v1", "visual_inspection", 2),
    ("openai_unified_balanced_v1", "text_analysis", 2),
    ("openai_unified_balanced_v1", "search_synthesis", 1),
    ("openai_unified_balanced_v1", "visual_inspection", 2),
    ("gemini_unified_v1", "text_analysis", 2),
    ("gemini_unified_v1", "search_synthesis", 1),
    ("gemini_unified_v1", "visual_inspection", 2),
    ("groq_split_v1", "text_analysis", 2),
    ("groq_split_v1", "search_synthesis", 1),
    ("groq_split_v1", "visual_inspection", 2),
    ("baseline_current_text_v1", "text_analysis", 2),
)
_PLANNED_DISCOVERY_MATRIX = (
    ("openai_unified_premium_v1", "provider_native_url_discovery", 1),
    ("openai_unified_balanced_v1", "provider_native_url_discovery", 1),
    ("gemini_unified_v1", "provider_native_url_discovery", 1),
    ("groq_split_v1", "provider_native_url_discovery", 1),
)
_INELIGIBLE_RETRIEVAL = (
    ("openai_unified_premium_v1", "search_retrieval"),
    ("openai_unified_balanced_v1", "search_retrieval"),
    ("gemini_unified_v1", "search_retrieval"),
    ("groq_split_v1", "search_retrieval"),
)
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
    "dated_official_pricing_schedules_and_explicit_cost_unknowns",
    "ps1_discovery_refetch_classification_extraction_and_support",
    "approved_us_operation_and_restricted_local_storage_binding",
    "same_day_lifecycle_and_pricing_checklist_prepared",
)
_TECHNICAL_BLOCKERS = (
    "provider_native_url_discovery_request_adapter_extraction_and_result_binding",
)
_HUMAN_GATES = (
    "provider_native_url_discovery_configuration_governance",
    "pilot_budget_ceiling_authorization",
    "credential_authorization_handling_and_scope",
    "explicit_pilot_authorization",
)
_LIVE_GATES = ("same_day_provider_lifecycle_and_pricing_certification",)
_PS1_BLOCKERS: tuple[str, ...] = ()
_PS1_REUSE = (
    "bounded_ssrf_safe_fetch_transport",
    "strict_url_security_and_redirect_auth_classification",
    "deterministic_retrieval_ordinals_source_ids_and_evidence_ids",
    "restricted_exact_trace_and_safe_ordinary_projection",
    "safe_search_tool_result_record",
)
_SAME_DAY_CHECKLIST = (
    "current_model_or_snapshot_availability_and_lifecycle",
    "api_endpoint_version_and_required_tool_availability",
    "announced_deprecation_or_shutdown_status",
    "required_schema_search_image_and_tool_combination_support",
    "official_pricing_schedule_and_current_rate_binding",
    "frozen_request_configuration_validity",
    "approved_standard_global_region_mode_compatibility",
)
_SAME_DAY_EVIDENCE_REQUIRED_FIELDS = (
    "candidate_id",
    "workload_stage_or_component",
    "model_or_snapshot",
    "endpoint_or_api_version",
    "request_configuration_id",
    "request_configuration_hash",
    "official_source_ids",
    "official_source_urls",
    "observed_at_utc",
    "lifecycle_status",
    "pricing_status",
    "request_configuration_status",
    "blockers",
)
_CANDIDATE_MODEL_MATRIX = (
    ("openai_unified_premium_v1", ("gpt-5.6-sol",)),
    ("openai_unified_balanced_v1", ("gpt-5.6-terra",)),
    ("gemini_unified_v1", ("gemini-3.7-flash",)),
    (
        "groq_split_v1",
        ("openai/gpt-oss-120b", "groq/compound", "qwen/qwen3.8-27b"),
    ),
    ("baseline_current_text_v1", ("openai/gpt-oss-120b",)),
)
_PILOT_FIXTURE_IDS = ("PT1", "PT2", "PS1", "PV1", "PV2", "PF1")
_CANDIDATE_SPECIFIC_BLOCKERS = (
    (
        "openai_unified_premium_v1",
        ("provider_native_url_discovery_request_configuration",),
    ),
    (
        "openai_unified_balanced_v1",
        ("provider_native_url_discovery_request_configuration",),
    ),
    (
        "gemini_unified_v1",
        (
            "provider_native_url_discovery_request_configuration",
            "billable_search_query_count_and_shared_allowance_state",
        ),
    ),
    (
        "groq_split_v1",
        (
            "provider_native_url_discovery_request_configuration",
            "compound_official_pricing_and_internal_topology",
            "qwen_preview_same_day_lifecycle",
        ),
    ),
)


class PilotPreflightError(ValueError):
    """A required frozen identity or provider-free prerequisite is stale."""


@dataclass(frozen=True, slots=True)
class ProviderNeutralPilotPreflight:
    status: str
    provider_free_common_preflight_ready: bool
    ready_awaiting_only_human_and_live_gates: bool
    resolved_components: tuple[str, ...]
    provider_free_technical_blockers: tuple[str, ...]
    pending_human_gates: tuple[str, ...]
    pending_live_gates: tuple[str, ...]
    configured_stage_matrix: tuple[tuple[str, str, int], ...]
    planned_discovery_matrix: tuple[tuple[str, str, int], ...]
    eligible_discovery_matrix: tuple[tuple[str, str, int], ...]
    ineligible_stage_matrix: tuple[tuple[str, str], ...]
    candidate_specific_blockers: tuple[tuple[str, tuple[str, ...]], ...]
    candidate_model_matrix: tuple[tuple[str, tuple[str, ...]], ...]
    pilot_fixture_ids: tuple[str, ...]
    same_day_checklist: tuple[str, ...]
    same_day_evidence_required_fields: tuple[str, ...]
    ps1_provider_free_blockers: tuple[str, ...]
    ps1_reusable_primitives: tuple[str, ...]
    provider_calls_in_currently_configured_non_search_scope: int
    configured_provider_calls: int
    planned_provider_calls: int
    maximum_configured_physical_attempts: int
    maximum_planned_physical_attempts: int
    cost_envelope_hash: str
    known_two_attempt_cost_subtotal_usd: str
    nominal_total_cost_usd: str | None
    conservative_maximum_total_cost_usd: str | None
    recommended_budget_ceiling_usd: str
    budget_authorization_status: str
    authoritative_execution_state: str
    same_day_lifecycle_recheck_required: bool = True
    ps1_built_in_search_evidence_eligible: bool = False
    ps1_provider_native_url_discovery_capability_approved: bool = True
    ps1_provider_native_url_discovery_configured_eligible: bool = False
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


def _verify_experiment_and_fixture_inventory() -> None:
    if (
        hashlib.sha256((_ARTIFACTS / "experiment.v1.json").read_bytes()).hexdigest()
        != _EXPERIMENT_FILE_SHA256
        or hashlib.sha256(
            (_ARTIFACTS / "pilot-fixtures.v1.json").read_bytes()
        ).hexdigest()
        != _PILOT_FIXTURE_FILE_SHA256
    ):
        raise PilotPreflightError("experiment_or_pilot_fixture_identity")
    experiment = _load("experiment.v1.json")
    gate = experiment.get("execution_gate")
    if (
        type(gate) is not dict
        or gate.get("authoritative_for_all_provider_execution") is not True
        or gate.get("overall_status") != "blocked_pre_execution"
        or gate.get("provider_calls_allowed") is not False
        or gate.get("pilot_calls_allowed") is not False
        or gate.get("scored_calls_allowed") is not False
        or experiment.get("provider_calls_completed") != 0
        or experiment.get("scored_provider_calls_completed") != 0
        or experiment.get("winner_selected") is not False
    ):
        raise PilotPreflightError("experiment_execution_gate")

    model_matrix: list[tuple[str, tuple[str, ...]]] = []
    architectures = experiment.get("candidate_architectures")
    baselines = experiment.get("baseline_architectures")
    if type(architectures) is not list or type(baselines) is not list:
        raise PilotPreflightError("experiment_candidate_inventory")
    for architecture in [*architectures, *baselines]:
        if type(architecture) is not dict:
            raise PilotPreflightError("experiment_candidate_inventory")
        candidate_id = architecture.get("candidate_id")
        workloads = architecture.get("workload_eligibility")
        if type(candidate_id) is not str or type(workloads) is not dict:
            raise PilotPreflightError("experiment_candidate_inventory")
        ordered_models: list[str] = []
        for workload_name in ("text", "search_price", "visual"):
            workload = workloads.get(workload_name)
            if type(workload) is not dict:
                raise PilotPreflightError("experiment_candidate_inventory")
            model = workload.get("model")
            if workload.get("eligible") is True:
                if type(model) is not str:
                    raise PilotPreflightError("experiment_candidate_inventory")
                if model not in ordered_models:
                    ordered_models.append(model)
        model_matrix.append((candidate_id, tuple(ordered_models)))
    if tuple(model_matrix) != _CANDIDATE_MODEL_MATRIX:
        raise PilotPreflightError("experiment_candidate_inventory")

    pilot = _load("pilot-fixtures.v1.json")
    fixtures = pilot.get("pilot_fixtures")
    if (
        type(fixtures) is not list
        or any(type(item) is not dict for item in fixtures)
        or tuple(item.get("id") for item in fixtures if type(item) is dict)
        != _PILOT_FIXTURE_IDS
        or pilot.get("provider_calls_completed") != 0
        or pilot.get("scored_result_eligible") is not False
        or pilot.get("quality_scoring_enabled") is not False
        or pilot.get("provider_calls_allowed") is not False
    ):
        raise PilotPreflightError("pilot_fixture_inventory")


def assess_provider_neutral_pilot_preflight() -> ProviderNeutralPilotPreflight:
    """Verify all currently resolved provider-free pilot inputs."""
    _verify_experiment_and_fixture_inventory()
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
    cost = verify_pilot_cost_envelope()
    if cost.semantic_hash != COST_ENVELOPE_HASH:
        raise PilotPreflightError("cost_envelope_identity")

    non_search = sum(
        fixture_count
        for _, stage, fixture_count in _CONFIGURED_STAGE_MATRIX
        if stage != "search_synthesis"
    )
    search = sum(
        fixture_count
        for _, stage, fixture_count in _CONFIGURED_STAGE_MATRIX
        if stage == "search_synthesis"
    )
    discovery = sum(item[2] for item in _PLANNED_DISCOVERY_MATRIX)
    configured = non_search + search
    planned = non_search + search + discovery
    return ProviderNeutralPilotPreflight(
        status="construction_blocked_pending_discovery_configuration",
        provider_free_common_preflight_ready=False,
        ready_awaiting_only_human_and_live_gates=False,
        resolved_components=_RESOLVED_COMPONENTS,
        provider_free_technical_blockers=_TECHNICAL_BLOCKERS,
        pending_human_gates=_HUMAN_GATES,
        pending_live_gates=_LIVE_GATES,
        configured_stage_matrix=_CONFIGURED_STAGE_MATRIX,
        planned_discovery_matrix=_PLANNED_DISCOVERY_MATRIX,
        eligible_discovery_matrix=(),
        ineligible_stage_matrix=_INELIGIBLE_RETRIEVAL,
        candidate_specific_blockers=_CANDIDATE_SPECIFIC_BLOCKERS,
        candidate_model_matrix=_CANDIDATE_MODEL_MATRIX,
        pilot_fixture_ids=_PILOT_FIXTURE_IDS,
        same_day_checklist=_SAME_DAY_CHECKLIST,
        same_day_evidence_required_fields=_SAME_DAY_EVIDENCE_REQUIRED_FIELDS,
        ps1_provider_free_blockers=_PS1_BLOCKERS,
        ps1_reusable_primitives=_PS1_REUSE,
        provider_calls_in_currently_configured_non_search_scope=non_search,
        configured_provider_calls=configured,
        planned_provider_calls=planned,
        maximum_configured_physical_attempts=configured * 2,
        maximum_planned_physical_attempts=planned * 2,
        cost_envelope_hash=cost.semantic_hash,
        known_two_attempt_cost_subtotal_usd=str(
            cost.known_charge_subtotal_two_attempts
        ),
        nominal_total_cost_usd=None,
        conservative_maximum_total_cost_usd=None,
        recommended_budget_ceiling_usd=str(cost.recommended_budget_ceiling_usd),
        budget_authorization_status=cost.budget_authorization_status,
        authoritative_execution_state="blocked_pre_execution",
        operation_country_code=region.operation_country_code,
        provider_service_mode=region.provider_service_mode,
        restricted_storage_country_code=region.restricted_storage_country_code,
        cross_region_replication_allowed=region.cross_region_replication_allowed,
    )
