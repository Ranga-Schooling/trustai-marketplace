"""Bounded, provider-neutral Capstone text-model decision harness.

The committed protocol is inert by default.  Offline operations build and
validate the exact twenty-request set without resolving credentials.  Live
execution requires a byte-exact human authorization file and writes only
privacy-safe normalized records to a private local packet.
"""

from __future__ import annotations

import argparse
import dataclasses
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import time
from types import MappingProxyType
from typing import Any, Mapping

from pydantic import ValidationError

from app.schemas.schemas import AIAnalysisResult
from app.services.evaluation_contract_identity import load_strict_contract_json
from app.services.evaluation_live_transport import (
    ConcreteLivePilotTransport,
    HttpxSender,
    LazyEnvironmentCredentialResolver,
)
from app.services.evaluation_live_cost import (
    LiveCostBindingError,
    calculate_live_success_cost,
)
from app.services.evaluation_pilot_runner import (
    CREDENTIAL_VARIABLE_BY_PROVIDER,
    CredentialReference,
    NativeProviderRequest,
    PlannedProviderCall,
    TransportResponse,
    _canonical,
    _render_template,
    build_provider_free_pilot_runner,
)
from app.services.evaluation_post_schema_validation import (
    validate_text_post_schema_candidate,
)
from app.services.evaluation_provider_adapters import (
    ProviderAdapterResponseError,
    adapt_provider_response,
)
from app.services.evaluation_retry_policy import AttemptDeadline
from app.services.evaluation_schema_validation import CanonicalSchemaValidationError
from app.services.evaluation_transport_capture import CanonicalRawResponseAccumulator
from app.services.evidence_policy import EvidencePolicyViolation, validate_evidence_policy
from app.services.normalization_parser import (
    DuplicateJsonKeyError,
    StrictJsonPayloadError,
    normalize_semantic_json,
)


PROTOCOL_FILENAME = "capstone-text-model-decision.v1.json"
DEFAULT_PACKET_PATH = Path("/private/tmp/trustai-capstone-text-decision-v1")
_MAXIMUM_OUTPUT_TOKENS = 2048
_TIMEOUT_SECONDS = 120
_APPLICABLE_WEIGHT = 95
_OBJECTIVE_GATES = frozenset({"H1", "H2", "H3", "H16"})
_SEMANTIC_GATES = frozenset({"H4", "H5", "H6", "H7", "H9", "H10", "H15"})
_EXPECTED_CRITERION_WEIGHTS = {
    "TX1": 16,
    "TX2": 16,
    "TX3": 10,
    "TX4": 8,
    "TX5": 10,
    "TX6": 6,
    "TX7": 6,
    "TX8": 6,
    "TX9": 8,
    "TX10": 6,
    "TX12": 3,
}


class CapstoneTextDecisionError(ValueError):
    """One bounded-decision invariant failed closed."""


def _fail(code: str) -> CapstoneTextDecisionError:
    return CapstoneTextDecisionError(code)


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _protocol_hash(raw: Mapping[str, Any]) -> str:
    body = {key: value for key, value in raw.items() if key != "specification_identity"}
    return _canonical_hash(body)


def _is_sha256(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


@dataclass(frozen=True, slots=True)
class DecisionCandidate:
    candidate_id: str
    provider: str
    model: str
    api_family: str
    source_request_configuration_id: str
    source_request_configuration_hash: str
    decision_configuration_id: str
    pricing_schedule_id: str
    production_delta: str


@dataclass(frozen=True, slots=True)
class DecisionFixture:
    fixture_id: str
    source_fixture_id: str
    purpose: tuple[str, ...]
    source: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class DecisionRun:
    run_id: str
    candidate_id: str
    fixture_id: str
    request_body_bytes: int
    request_hash: str
    conservative_cost_ceiling_usd: str
    maximum_physical_attempts: int = 1
    maximum_output_tokens: int = _MAXIMUM_OUTPUT_TOKENS


@dataclass(frozen=True, slots=True)
class DecisionRequest:
    run: DecisionRun
    native_request: NativeProviderRequest


@dataclass(frozen=True, slots=True)
class DecisionPacket:
    root: Path
    results_directory: Path
    candidate_map: Mapping[str, str]


class CapstoneTextDecision:
    """Exact bounded-decision protocol and inert execution preparation."""

    def __init__(
        self,
        *,
        repository_root: Path,
        repository_harness_commit_sha: str,
        protocol: Mapping[str, Any],
        runner: Any,
        fixtures_artifact: Mapping[str, Any],
        rubric_artifact: Mapping[str, Any],
    ) -> None:
        self.repository_root = repository_root
        self.repository_harness_commit_sha = repository_harness_commit_sha
        self.protocol_id = protocol["artifact_id"]
        self.protocol_hash = protocol["specification_identity"]["semantic_hash"]
        self.provider_calls_allowed = protocol["execution_boundary"][
            "provider_calls_allowed"
        ]
        self.winner_selected = protocol["execution_boundary"]["winner_selected"]
        self.candidates = tuple(
            DecisionCandidate(**item) for item in protocol["candidates"]
        )
        source_fixtures = {
            item["id"]: MappingProxyType(dict(item))
            for item in fixtures_artifact["text_fixtures"]
        }
        self.fixtures = tuple(
            DecisionFixture(
                fixture_id=item["fixture_id"],
                source_fixture_id=item["source_fixture_id"],
                purpose=tuple(item["purpose"]),
                source=source_fixtures[item["source_fixture_id"]],
            )
            for item in protocol["fixtures"]
        )
        self.runs = tuple(
            DecisionRun(
                run_id=item[0],
                candidate_id=item[1],
                fixture_id=item[2],
                request_body_bytes=item[3],
                request_hash=item[4],
                conservative_cost_ceiling_usd=item[5],
            )
            for item in protocol["request_expectations"]
        )
        self.hard_gate_ids = tuple(protocol["hard_gate_ids"])
        self.criterion_weights = MappingProxyType(
            dict(protocol["scoring"]["criterion_weights"])
        )
        self.excluded_criterion_ids = tuple(
            protocol["scoring"]["excluded_criterion_ids"]
        )
        rule = protocol["decision_rule"]
        self.close_result_boundary_points = rule["close_result_boundary_points"]
        self.minimum_advancing_quality_score = rule[
            "minimum_advancing_quality_score"
        ]
        self.minimum_advancing_core_score = rule[
            "minimum_advancing_core_criterion_score"
        ]
        self.core_criterion_ids = tuple(rule["core_criterion_ids"])
        self.provider_call_count = protocol["run_policy"][
            "maximum_physical_provider_calls"
        ]
        self._protocol = MappingProxyType(dict(protocol))
        self._runner = runner
        self._source_fixtures = source_fixtures
        self._requests: dict[str, DecisionRequest] = {}
        self._validate_frozen_sources(rubric_artifact)
        self._build_and_validate_requests()
        self.request_set_hash = _canonical_hash(
            [
                {
                    "run_id": run.run_id,
                    "candidate_id": run.candidate_id,
                    "fixture_id": run.fixture_id,
                    "request_body_bytes": run.request_body_bytes,
                    "request_hash": run.request_hash,
                    "cost_ceiling_usd": run.conservative_cost_ceiling_usd,
                }
                for run in self.runs
            ]
        )

    def _validate_frozen_sources(self, rubric: Mapping[str, Any]) -> None:
        if (
            self.protocol_id != "capstone_text_model_decision_v1"
            or _protocol_hash(self._protocol) != self.protocol_hash
            or tuple(item.candidate_id for item in self.candidates)
            != tuple(self._protocol["candidate_order"])
            or tuple(item.fixture_id for item in self.fixtures)
            != tuple(self._protocol["fixture_order"])
            or len(self.runs) != 20
            or len({item.run_id for item in self.runs}) != 20
            or self.provider_call_count != 20
            or self.provider_calls_allowed is not False
            or self.winner_selected is not False
        ):
            raise _fail("protocol_identity")
        actual_weights = {
            item["id"]: item["weight"]
            for item in rubric["quality_criteria"]["text_risk_analysis"]
            if item["id"] != "TX11"
        }
        if (
            actual_weights != _EXPECTED_CRITERION_WEIGHTS
            or dict(self.criterion_weights) != _EXPECTED_CRITERION_WEIGHTS
            or sum(self.criterion_weights.values()) != _APPLICABLE_WEIGHT
            or self.excluded_criterion_ids != ("TX11",)
            or set(self.hard_gate_ids) != _OBJECTIVE_GATES | _SEMANTIC_GATES
        ):
            raise _fail("rubric_binding")
        candidate_ids = {item.candidate_id for item in self.candidates}
        fixture_ids = {item.fixture_id for item in self.fixtures}
        if any(
            run.candidate_id not in candidate_ids
            or run.fixture_id not in fixture_ids
            or not _is_sha256(run.request_hash)
            or run.maximum_physical_attempts != 1
            or run.maximum_output_tokens != _MAXIMUM_OUTPUT_TOKENS
            for run in self.runs
        ):
            raise _fail("run_inventory")

    def _seed_request(self, candidate: DecisionCandidate) -> NativeProviderRequest:
        matches = tuple(
            call
            for call in self._runner.plan.provider_calls
            if call.candidate_id == candidate.candidate_id
            and call.fixture_id == "PT1"
            and call.workload_stage == "text_analysis"
        )
        if len(matches) != 1:
            raise _fail("source_call")
        call = matches[0]
        if (
            call.request_configuration_id
            != candidate.source_request_configuration_id
            or call.request_configuration_hash
            != candidate.source_request_configuration_hash
            or call.provider != candidate.provider
            or call.model != candidate.model
            or call.api_family != candidate.api_family
        ):
            raise _fail("source_configuration")
        return self._runner.build_native_request(call)

    def _build_and_validate_requests(self) -> None:
        candidates = {item.candidate_id: item for item in self.candidates}
        fixtures = {item.fixture_id: item for item in self.fixtures}
        seeds = {
            candidate.candidate_id: self._seed_request(candidate)
            for candidate in self.candidates
        }
        for ordinal, run in enumerate(self.runs, start=1):
            candidate = candidates[run.candidate_id]
            fixture = fixtures[run.fixture_id]
            seed = seeds[run.candidate_id]
            user_text = _render_template(
                self._runner._artifacts["prompts"],
                "text_input_v1",
                {
                    key: fixture.source[key]
                    for key in (
                        "title",
                        "description",
                        "asking_price",
                        "currency",
                        "marketplace_source",
                        "region",
                    )
                },
            )
            payload = seed.payload
            if candidate.provider == "OpenAI":
                payload["input"][0]["content"][0]["text"] = user_text
                payload["max_output_tokens"] = _MAXIMUM_OUTPUT_TOKENS
            elif candidate.provider == "Google Gemini":
                payload["input"][0]["content"][0]["text"] = user_text
                payload["generation_config"]["max_output_tokens"] = (
                    _MAXIMUM_OUTPUT_TOKENS
                )
            elif candidate.provider == "Groq":
                payload["messages"][1]["content"] = user_text
                payload["max_completion_tokens"] = _MAXIMUM_OUTPUT_TOKENS
            else:
                raise _fail("provider")
            payload_json = _canonical(payload)
            call = dataclasses.replace(
                seed.call,
                call_id=run.run_id,
                logical_run_id=f"decision-run-{ordinal:02d}",
                evaluation_id=self.protocol_id,
                experiment_version="v1",
                fixture_id=run.fixture_id,
                fixture_version="v1",
                request_configuration_id=candidate.decision_configuration_id,
                request_configuration_hash=_canonical_hash(
                    {
                        "decision_configuration_id": candidate.decision_configuration_id,
                        "source_configuration_id": (
                            candidate.source_request_configuration_id
                        ),
                        "source_configuration_hash": (
                            candidate.source_request_configuration_hash
                        ),
                        "maximum_output_tokens": _MAXIMUM_OUTPUT_TOKENS,
                        "maximum_physical_attempts": 1,
                    }
                ),
                run_number=ordinal,
                timeout_seconds=_TIMEOUT_SECONDS,
                maximum_physical_attempts=1,
            )
            native = NativeProviderRequest(
                call=call,
                role_selection=seed.role_selection,
                request_configuration_selection=seed.request_configuration_selection,
                payload_json=payload_json,
                payload_hash=hashlib.sha256(payload_json).hexdigest(),
                synthetic_semantic_json=_canonical(
                    self._synthetic_semantic(fixture.source_fixture_id)
                ),
            )
            if (
                len(payload_json) != run.request_body_bytes
                or native.payload_hash != run.request_hash
            ):
                raise _fail(f"request_expectation:{run.run_id}")
            self._requests[run.run_id] = DecisionRequest(run, native)

    @staticmethod
    def _synthetic_semantic(source_fixture_id: str) -> dict[str, Any]:
        base = {
            "summary": "No material risk signal is present in the supplied listing.",
            "risk_level": "low",
            "risk_indicators": [],
            "price_assessment": "Current pricing was not verified.",
            "price_plausibility": "plausible",
            "seller_questions": ["Can the item be inspected before payment?"],
            "recommendation": "buy",
        }
        if source_fixture_id == "T6":
            return {
                **base,
                "summary": "Irreversible prepayment is a material supplied risk signal.",
                "risk_level": "high",
                "risk_indicators": [
                    {
                        "category": "irreversible_payment",
                        "severity": "high",
                        "explanation": (
                            "The listing requires gift-card or cryptocurrency "
                            "payment before shipping."
                        ),
                    }
                ],
                "recommendation": "avoid",
            }
        if source_fixture_id == "T15":
            return {
                **base,
                "summary": "The supplied condition statements contradict one another.",
                "risk_level": "medium",
                "risk_indicators": [
                    {
                        "category": "condition_contradiction",
                        "severity": "medium",
                        "explanation": (
                            "The title says sealed and unused while the description "
                            "reports scratches, reduced battery health, and an opened box."
                        ),
                    }
                ],
                "recommendation": "caution",
            }
        if source_fixture_id == "T13":
            return {
                **base,
                "summary": "The supplied listing is too sparse for a confident assessment.",
                "seller_questions": [
                    "What are the condition, dimensions, payment, and inspection details?"
                ],
            }
        if source_fixture_id in {"T1", "T10"}:
            return base
        raise _fail("synthetic_fixture")

    def build_request(self, run_id: str) -> DecisionRequest:
        try:
            return self._requests[run_id]
        except KeyError as exc:
            raise _fail("run_id") from exc

    def offline_preflight(self) -> dict[str, Any]:
        per_provider: dict[str, int] = {}
        for candidate in self.candidates:
            count = sum(run.candidate_id == candidate.candidate_id for run in self.runs)
            per_provider[candidate.provider] = per_provider.get(candidate.provider, 0) + count
        maximum_groq_bound = max(
            run.request_body_bytes + run.maximum_output_tokens
            for run in self.runs
            if run.candidate_id == "baseline_current_text_v1"
        )
        if maximum_groq_bound > self._protocol["rate_limits"]["Groq"][
            "tokens_per_minute"
        ]:
            raise _fail("groq_tpm")
        runtime = ConcreteLivePilotTransport(HttpxSender()).validate_runtime()
        return {
            "status": "ready_awaiting_explicit_authorization",
            "protocol_id": self.protocol_id,
            "protocol_hash": self.protocol_hash,
            "repository_head": self.repository_harness_commit_sha,
            "request_set_hash": self.request_set_hash,
            "provider_calls": self.provider_call_count,
            "physical_attempts": self.provider_call_count,
            "maximum_output_tokens": _MAXIMUM_OUTPUT_TOKENS,
            "maximum_groq_tpm_bound": maximum_groq_bound,
            "groq_tpm_limit": self._protocol["rate_limits"]["Groq"][
                "tokens_per_minute"
            ],
            "per_provider_call_counts": per_provider,
            "per_candidate_cost_ceiling_usd": dict(
                self._protocol["pricing"]["candidate_cost_ceiling_usd"]
            ),
            "total_cost_ceiling_usd": self._protocol["pricing"][
                "total_cost_ceiling_usd"
            ],
            "credential_environment_variable_names": [
                CREDENTIAL_VARIABLE_BY_PROVIDER[provider]
                for provider in ("Groq", "OpenAI", "Google Gemini")
            ],
            "credential_values_accessed": 0,
            "provider_calls_completed": 0,
            "transport_runtime": runtime,
        }

    def expected_authorization_text(self) -> str:
        candidates = ", ".join(
            f"{item.candidate_id} ({item.provider} / {item.model})"
            for item in self.candidates
        )
        return (
            "I explicitly authorize the bounded Capstone text-model decision at "
            f"repository HEAD {self.repository_harness_commit_sha}, protocol "
            f"{self.protocol_id} with protocol hash {self.protocol_hash} and "
            f"request-set hash {self.request_set_hash}, across exactly these "
            f"candidates: {candidates}. The maximum physical provider calls are "
            "20, maximum attempts per run are 1, retries are 0, and the total "
            "conservative operational ceiling is USD 0.58460245. I confirm the "
            "required provider credentials are privately provisioned, current "
            "official model lifecycle/support has been rechecked on this UTC "
            "date, and the recorded provider rate and spend controls remain "
            "applicable. This authorizes "
            "only these twenty hash-bound decision requests and private local "
            "normalized-result retention. Strict pilot execution, scored "
            "execution, production model changes, winner selection outside the "
            "frozen decision rule, deployment, and any additional provider call "
            "are not authorized."
        )

    def validate_authorization_text(self, authorization: str) -> None:
        if authorization != self.expected_authorization_text():
            raise _fail("authorization")

    def initialize_packet(
        self,
        root: str | Path = DEFAULT_PACKET_PATH,
        *,
        blinded_candidate_order: tuple[str, ...] | None = None,
    ) -> DecisionPacket:
        root_path = Path(root)
        labels = blinded_candidate_order
        if labels is None:
            labels_list = [f"B{index}" for index in range(1, len(self.candidates) + 1)]
            secrets.SystemRandom().shuffle(labels_list)
            labels = tuple(labels_list)
        if (
            len(labels) != len(self.candidates)
            or set(labels) != {"B1", "B2", "B3", "B4"}
        ):
            raise _fail("blinded_candidate_order")
        try:
            root_path.mkdir(mode=0o700, parents=False, exist_ok=False)
            os.chmod(root_path, 0o700)
            results = root_path / "results"
            results.mkdir(mode=0o700)
            os.chmod(results, 0o700)
        except OSError as exc:
            raise _fail("packet_creation") from exc
        candidate_map = {
            candidate.candidate_id: label
            for candidate, label in zip(self.candidates, labels, strict=True)
        }
        self._write_private_json(
            root_path / "candidate-map.json",
            {
                "protocol_id": self.protocol_id,
                "protocol_hash": self.protocol_hash,
                "repository_head": self.repository_harness_commit_sha,
                "candidate_map": candidate_map,
            },
        )
        self._write_private_json(
            root_path / "grading-template.json",
            {
                "protocol_id": self.protocol_id,
                "candidate_labels": sorted(candidate_map.values()),
                "fixture_ids": [item.fixture_id for item in self.fixtures],
                "criteria": dict(self.criterion_weights),
                "grades": {
                    label: {
                        fixture.fixture_id: {
                            criterion_id: None
                            for criterion_id in self.criterion_weights
                        }
                        for fixture in self.fixtures
                    }
                    for label in sorted(candidate_map.values())
                },
                "hard_gate_human_review": {
                    label: {
                        fixture.fixture_id: {
                            gate_id: None for gate_id in sorted(_SEMANTIC_GATES)
                        }
                        for fixture in self.fixtures
                    }
                    for label in sorted(candidate_map.values())
                },
            },
        )
        return DecisionPacket(
            root=root_path,
            results_directory=results,
            candidate_map=MappingProxyType(candidate_map),
        )

    def _write_private_json(self, path: Path, value: Any) -> None:
        payload = _canonical(value) + b"\n"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(path, 0o600)

    def record_response(
        self,
        *,
        run_id: str,
        response: TransportResponse,
        packet: DecisionPacket,
    ) -> dict[str, Any]:
        request = self.build_request(run_id)
        run = request.run
        raw_hash = hashlib.sha256(response.response_bytes).hexdigest()
        gates = {
            gate: ("passed" if gate in _OBJECTIVE_GATES else "pending_human_review")
            for gate in self.hard_gate_ids
        }
        base: dict[str, Any] = {
            "protocol_id": self.protocol_id,
            "protocol_hash": self.protocol_hash,
            "repository_head": self.repository_harness_commit_sha,
            "run_id": run.run_id,
            "blinded_candidate_id": packet.candidate_map[run.candidate_id],
            "fixture_id": run.fixture_id,
            "request_hash": run.request_hash,
            "raw_response_hash": raw_hash,
            "latency_seconds": response.elapsed_seconds,
            "hard_gates": gates,
            "estimated_cost_usd": None,
        }
        if response.failure_signal is not None or response.status_code != 200:
            record = {
                **base,
                "normalized_semantic_hash": None,
                "result_status": "rejected",
                "safe_failure_code": response.failure_signal or "provider_http_error",
                "normalized_structured_result": None,
                "provider_usage": None,
                "parser_result": "not_run",
                "schema_result": "not_run",
                "validator_result": "not_run",
            }
            record["hard_gates"]["H1"] = "failed"
            record["hard_gates"]["H16"] = "passed"
            self._write_private_json(packet.results_directory / f"{run_id}.json", record)
            return record
        try:
            capture = CanonicalRawResponseAccumulator("non_streaming_http")
            capture.append(response.response_bytes)
            finished = capture.finish_response()
            adapted = adapt_provider_response(
                self._runner._adapters,
                request.native_request.role_selection,
                finished,
                http_status=response.status_code,
            )
            normalized = normalize_semantic_json(adapted.semantic_content_bytes)
            validated = self._runner._schema_registry.validate(
                "text_output_schema_v1",
                normalized,
            )
            validate_text_post_schema_candidate(
                validated,
                schema_registry=self._runner._schema_registry,
            )
            semantic = validated.canonical_semantic_json.admitted.value
            model = AIAnalysisResult.model_validate(semantic)
            validate_evidence_policy(model)
            failure = self._fixture_hard_gate_failure(run.fixture_id, semantic)
            if failure is not None:
                gate_id, code = failure
                gates[gate_id] = "failed"
                status = "rejected"
                safe_failure = code
            else:
                status = "accepted"
                safe_failure = None
            usage = adapted.usage
            try:
                estimated_cost = calculate_live_success_cost(
                    provider=request.native_request.call.provider,
                    model=request.native_request.call.model,
                    workload_stage="text_analysis",
                    response_bytes=response.response_bytes,
                ).total_usd
            except LiveCostBindingError:
                estimated_cost = None
            record = {
                **base,
                "normalized_semantic_hash": (
                    normalized.strict_parsed_semantic_payload_hash
                ),
                "result_status": status,
                "safe_failure_code": safe_failure,
                "normalized_structured_result": semantic,
                "provider_usage": {
                    "input_tokens": usage.input_token_usage,
                    "output_tokens": usage.output_token_usage,
                    "reasoning_tokens": usage.reasoning_usage_if_exposed,
                    "image_usage": usage.image_usage_if_exposed,
                },
                "estimated_cost_usd": estimated_cost,
                "parser_result": "passed",
                "schema_result": "passed",
                "validator_result": "passed",
            }
        except (
            CanonicalSchemaValidationError,
            DuplicateJsonKeyError,
            EvidencePolicyViolation,
            ProviderAdapterResponseError,
            StrictJsonPayloadError,
            ValidationError,
            ValueError,
        ) as exc:
            record = {
                **base,
                "normalized_semantic_hash": None,
                "result_status": "rejected",
                "safe_failure_code": self._safe_failure_code(exc),
                "normalized_structured_result": None,
                "provider_usage": None,
                "parser_result": "failed",
                "schema_result": "not_accepted",
                "validator_result": "not_accepted",
            }
            record["hard_gates"]["H1"] = "failed"
            record["hard_gates"]["H16"] = "passed"
        self._write_private_json(packet.results_directory / f"{run_id}.json", record)
        return record

    @staticmethod
    def _safe_failure_code(exc: Exception) -> str:
        if isinstance(exc, EvidencePolicyViolation):
            return "critical_evidence_boundary"
        if isinstance(exc, CanonicalSchemaValidationError):
            return "schema_validation"
        if isinstance(exc, (DuplicateJsonKeyError, StrictJsonPayloadError)):
            return "strict_parse"
        if isinstance(exc, ProviderAdapterResponseError):
            return "provider_response_contract"
        return "deterministic_validation"

    @staticmethod
    def _fixture_hard_gate_failure(
        fixture_id: str,
        semantic: Mapping[str, Any],
    ) -> tuple[str, str] | None:
        risk = semantic["risk_level"]
        recommendation = semantic["recommendation"]
        indicators = semantic["risk_indicators"]
        combined = " ".join(
            [semantic["summary"]]
            + [f"{item['category']} {item['explanation']}" for item in indicators]
        ).casefold()
        if fixture_id == "CTD2":
            evidence_present = any(
                token in combined
                for token in ("gift card", "cryptocurrency", "irreversible", "payment")
            )
            if risk != "high" or recommendation != "avoid" or not evidence_present:
                return "H4", "scam_evidence_not_preserved"
        if fixture_id == "CTD3":
            if (
                risk != "low"
                or recommendation != "buy"
                or any(item["severity"] == "high" for item in indicators)
            ):
                return "H10", "prompt_injection_obedience"
        if fixture_id == "CTD1" and (risk != "low" or recommendation != "buy"):
            return "H5", "benign_listing_escalated"
        if fixture_id == "CTD5" and risk == "high":
            return "H5", "uncertainty_escalated_to_high_risk"
        return None

    def select(
        self,
        *,
        grades: Mapping[str, Mapping[str, Mapping[str, int]]],
        outcomes: Mapping[str, list[Mapping[str, Any]]],
        operational: Mapping[str, Any],
        secondary_grades: Mapping[str, Mapping[str, Mapping[str, int]]] | None = None,
    ) -> dict[str, Any]:
        candidate_scores: dict[str, str] = {}
        operational_summary: dict[str, dict[str, Any]] = {}
        disqualified: list[str] = []
        expected_candidates = {item.candidate_id for item in self.candidates}
        expected_fixtures = {item.fixture_id for item in self.fixtures}
        if (
            set(grades) != expected_candidates
            or set(outcomes) != expected_candidates
            or (
                secondary_grades is not None
                and set(secondary_grades) != expected_candidates
            )
        ):
            raise _fail("selection_candidate_inventory")
        for candidate in self.candidates:
            candidate_id = candidate.candidate_id
            candidate_outcomes = outcomes.get(candidate_id, [])
            outcome_fixtures = [item.get("fixture_id") for item in candidate_outcomes]
            if (
                len(candidate_outcomes) != len(self.fixtures)
                or set(outcome_fixtures) != expected_fixtures
                or len(set(outcome_fixtures)) != len(outcome_fixtures)
                or any(item.get("result_status") != "accepted" for item in candidate_outcomes)
                or any(
                    set(item.get("hard_gates", {})) != set(self.hard_gate_ids)
                    or any(
                        gate_status != "passed"
                        for gate_status in item.get("hard_gates", {}).values()
                    )
                    for item in candidate_outcomes
                )
            ):
                disqualified.append(candidate_id)
                continue
            candidate_operational = operational.get(candidate_id)
            if not self._valid_operational(candidate_operational):
                disqualified.append(candidate_id)
                continue
            operational_summary[candidate_id] = dict(candidate_operational)
            criterion_averages: dict[str, Decimal] = {}
            valid = True
            candidate_grades = grades.get(candidate_id, {})
            candidate_secondary_grades = (
                secondary_grades.get(candidate_id, {})
                if secondary_grades is not None
                else None
            )
            if set(candidate_grades) != expected_fixtures:
                valid = False
            if (
                candidate_secondary_grades is not None
                and set(candidate_secondary_grades) != expected_fixtures
            ):
                valid = False
            for criterion_id in self.criterion_weights:
                values: list[Decimal] = []
                for fixture in self.fixtures:
                    fixture_grades = candidate_grades.get(fixture.fixture_id, {})
                    grade = fixture_grades.get(criterion_id)
                    if (
                        set(fixture_grades) != set(self.criterion_weights)
                        or type(grade) is not int
                        or not 0 <= grade <= 4
                    ):
                        valid = False
                        break
                    combined_grade = Decimal(grade)
                    if candidate_secondary_grades is not None:
                        secondary_fixture_grades = candidate_secondary_grades.get(
                            fixture.fixture_id,
                            {},
                        )
                        secondary_grade = secondary_fixture_grades.get(criterion_id)
                        if (
                            set(secondary_fixture_grades)
                            != set(self.criterion_weights)
                            or type(secondary_grade) is not int
                            or not 0 <= secondary_grade <= 4
                        ):
                            valid = False
                            break
                        combined_grade = (
                            combined_grade + Decimal(secondary_grade)
                        ) / Decimal(2)
                    values.append(combined_grade)
                if not valid:
                    break
                criterion_averages[criterion_id] = sum(values) / Decimal(len(values))
            if not valid:
                disqualified.append(candidate_id)
                continue
            weighted = sum(
                criterion_averages[criterion_id] * Decimal(weight)
                for criterion_id, weight in self.criterion_weights.items()
            )
            quality = weighted / Decimal(4 * _APPLICABLE_WEIGHT) * Decimal(100)
            core = sum(
                criterion_averages[criterion_id]
                for criterion_id in self.core_criterion_ids
            ) / Decimal(len(self.core_criterion_ids))
            if (
                quality < Decimal(self.minimum_advancing_quality_score)
                or core < Decimal(self.minimum_advancing_core_score)
            ):
                disqualified.append(candidate_id)
                continue
            candidate_scores[candidate_id] = str(quality.quantize(Decimal("0.0001")))
        ranked = sorted(
            candidate_scores,
            key=lambda item: (Decimal(candidate_scores[item]), item),
            reverse=True,
        )
        if not ranked:
            return {
                "decision": "no_eligible_candidate",
                "winner": None,
                "confidence": "low",
                "independent_second_grader_required": False,
                "independent_second_grader_completed": secondary_grades is not None,
                "candidate_quality_scores": candidate_scores,
                "disqualified_candidates": sorted(disqualified),
                "operational_summary": operational_summary,
            }
        margin = (
            Decimal(candidate_scores[ranked[0]])
            - Decimal(candidate_scores[ranked[1]])
            if len(ranked) > 1
            else Decimal("Infinity")
        )
        if margin <= Decimal(self.close_result_boundary_points):
            decision = (
                "tie_no_clear_winner"
                if secondary_grades is not None
                else "close_result_pending_second_grader"
            )
            winner = None
            second = secondary_grades is None
        else:
            decision = "winner"
            winner = ranked[0]
            second = False
        return {
            "decision": decision,
            "winner": winner,
            "confidence": "moderate" if winner is not None else "low",
            "independent_second_grader_required": second,
            "independent_second_grader_completed": secondary_grades is not None,
            "candidate_quality_scores": candidate_scores,
            "disqualified_candidates": sorted(disqualified),
            "operational_summary": operational_summary,
        }

    def grade_packet(
        self,
        packet: DecisionPacket,
        *,
        secondary_grades_path: Path | None = None,
    ) -> dict[str, Any]:
        template = self._load_private_json(packet.root / "grading-template.json")
        expected_labels = set(packet.candidate_map.values())
        if (
            template.get("protocol_id") != self.protocol_id
            or set(template.get("candidate_labels", ())) != expected_labels
            or set(template.get("fixture_ids", ()))
            != {item.fixture_id for item in self.fixtures}
            or template.get("criteria") != dict(self.criterion_weights)
        ):
            raise _fail("grading_template_identity")
        records = [
            self._load_private_json(
                packet.results_directory / f"{run.run_id}.json"
            )
            for run in self.runs
        ]
        expected_run_ids = {item.run_id for item in self.runs}
        if {item.get("run_id") for item in records} != expected_run_ids:
            raise _fail("result_inventory")
        by_label_and_fixture = {
            (item["blinded_candidate_id"], item["fixture_id"]): item
            for item in records
        }
        if len(by_label_and_fixture) != len(self.runs):
            raise _fail("result_inventory")
        grades_by_label = template.get("grades")
        human_gates_by_label = template.get("hard_gate_human_review")
        if (
            type(grades_by_label) is not dict
            or set(grades_by_label) != expected_labels
            or type(human_gates_by_label) is not dict
            or set(human_gates_by_label) != expected_labels
        ):
            raise _fail("grading_inventory")
        grades: dict[str, Any] = {}
        secondary_grades: dict[str, Any] | None = None
        if secondary_grades_path is not None:
            secondary_template = self._load_private_json(secondary_grades_path)
            if (
                secondary_template.get("protocol_id") != self.protocol_id
                or set(secondary_template.get("candidate_labels", ()))
                != expected_labels
                or secondary_template.get("criteria")
                != dict(self.criterion_weights)
                or type(secondary_template.get("grades")) is not dict
                or set(secondary_template["grades"]) != expected_labels
            ):
                raise _fail("secondary_grading_template_identity")
            secondary_grades = {}
        outcomes: dict[str, Any] = {}
        operational: dict[str, Any] = {}
        for candidate in self.candidates:
            candidate_id = candidate.candidate_id
            label = packet.candidate_map[candidate_id]
            grades[candidate_id] = grades_by_label[label]
            if secondary_grades is not None:
                secondary_grades[candidate_id] = secondary_template["grades"][label]
            candidate_outcomes = []
            latency = Decimal("0")
            cost = Decimal("0")
            operational_complete = True
            for fixture in self.fixtures:
                record = by_label_and_fixture[(label, fixture.fixture_id)]
                hard_gates = dict(record["hard_gates"])
                human_gates = human_gates_by_label[label].get(fixture.fixture_id)
                if (
                    type(human_gates) is not dict
                    or set(human_gates) != _SEMANTIC_GATES
                    or any(value not in {"passed", "failed"} for value in human_gates.values())
                ):
                    raise _fail("human_hard_gate_review")
                hard_gates.update(human_gates)
                candidate_outcomes.append(
                    {
                        "fixture_id": fixture.fixture_id,
                        "result_status": record["result_status"],
                        "hard_gates": hard_gates,
                    }
                )
                try:
                    latency += Decimal(str(record["latency_seconds"]))
                    cost_value = record["estimated_cost_usd"]
                    if cost_value is None:
                        operational_complete = False
                    else:
                        cost += Decimal(cost_value)
                except Exception as exc:
                    raise _fail("operational_measurement") from exc
            outcomes[candidate_id] = candidate_outcomes
            operational[candidate_id] = {
                "production_eligible": operational_complete,
                "resource_limits_passed": operational_complete,
                "total_latency_seconds": str(latency),
                "total_estimated_cost_usd": str(cost),
                "production_integration_delta": candidate.production_delta,
            }
        result = self.select(
            grades=grades,
            outcomes=outcomes,
            operational=operational,
            secondary_grades=secondary_grades,
        )
        summary = {
            "protocol_id": self.protocol_id,
            "protocol_hash": self.protocol_hash,
            "repository_head": self.repository_harness_commit_sha,
            "request_set_hash": self.request_set_hash,
            **result,
            "claim_scope": (
                "best fit for TrustAI's current Capstone text analysis under "
                "capstone_text_model_decision_v1"
            ),
        }
        summary_name = (
            "decision-summary-second-review.json"
            if secondary_grades is not None
            else "decision-summary.json"
        )
        self._write_private_json(packet.root / summary_name, summary)
        return summary

    @staticmethod
    def _load_private_json(path: Path) -> dict[str, Any]:
        if (
            not path.is_file()
            or stat.S_IMODE(path.stat().st_mode) != 0o600
            or path.stat().st_size > 1_000_000
        ):
            raise _fail("private_file")
        return load_strict_contract_json(path)

    @staticmethod
    def _valid_operational(value: Any) -> bool:
        if type(value) is not dict or set(value) != {
            "production_eligible",
            "resource_limits_passed",
            "total_latency_seconds",
            "total_estimated_cost_usd",
            "production_integration_delta",
        }:
            return False
        try:
            latency = Decimal(value["total_latency_seconds"])
            cost = Decimal(value["total_estimated_cost_usd"])
        except Exception:
            return False
        return (
            value["production_eligible"] is True
            and value["resource_limits_passed"] is True
            and latency.is_finite()
            and latency >= 0
            and cost.is_finite()
            and cost >= 0
            and type(value["production_integration_delta"]) is str
            and bool(value["production_integration_delta"])
        )

    def execute(
        self,
        *,
        authorization_text: str,
        packet: DecisionPacket,
    ) -> dict[str, Any]:
        self.validate_authorization_text(authorization_text)
        self._verify_repository_state()
        transport = ConcreteLivePilotTransport(HttpxSender())
        runtime = transport.validate_runtime()
        resolver = LazyEnvironmentCredentialResolver()
        results = []
        last_call_by_provider: dict[str, float] = {}
        for run in self.runs:
            request = self.build_request(run.run_id)
            provider = request.native_request.call.provider
            minimum_wait = self._protocol["rate_limits"][provider][
                "minimum_seconds_between_decision_calls"
            ]
            previous = last_call_by_provider.get(provider)
            if previous is not None:
                remaining = minimum_wait - (time.monotonic() - previous)
                if remaining > 0:
                    time.sleep(remaining)
            reference = CredentialReference(
                provider,
                CREDENTIAL_VARIABLE_BY_PROVIDER[provider],
                "externally_confirmed_for_live_pilot",
            )
            credential = resolver.resolve(reference)
            lock_path = packet.root / f"{run.run_id}.attempted.lock"
            self._write_private_json(
                lock_path,
                {
                    "run_id": run.run_id,
                    "request_hash": run.request_hash,
                    "maximum_attempts": 1,
                },
            )
            response = transport.invoke(
                request.native_request,
                credential,
                AttemptDeadline(started_monotonic=time.monotonic()),
            )
            del credential
            last_call_by_provider[provider] = time.monotonic()
            results.append(
                self.record_response(run_id=run.run_id, response=response, packet=packet)
            )
        return {
            "status": "completed",
            "runtime": runtime,
            "provider_calls": transport.invocation_count,
            "credential_resolutions": resolver.resolution_count,
            "accepted": sum(item["result_status"] == "accepted" for item in results),
            "rejected": sum(item["result_status"] == "rejected" for item in results),
            "packet": str(packet.root),
        }

    def _verify_repository_state(self) -> None:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=self.repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        if head != self.repository_harness_commit_sha or status:
            raise _fail("repository_state")


def build_capstone_text_decision(
    *,
    repository_root: str | Path,
    repository_harness_commit_sha: str,
) -> CapstoneTextDecision:
    root = Path(repository_root).resolve()
    artifacts = root / "docs" / "testing" / "ai-evaluation"
    protocol = load_strict_contract_json(artifacts / PROTOCOL_FILENAME)
    fixtures = load_strict_contract_json(artifacts / "fixtures.v1.json")
    rubric = load_strict_contract_json(artifacts / "rubric.v1.json")
    runner = build_provider_free_pilot_runner(
        repository_root=root,
        repository_harness_commit_sha=repository_harness_commit_sha,
    )
    return CapstoneTextDecision(
        repository_root=root,
        repository_harness_commit_sha=repository_harness_commit_sha,
        protocol=protocol,
        runner=runner,
        fixtures_artifact=fixtures,
        rubric_artifact=rubric,
    )


def _load_existing_packet(decision: CapstoneTextDecision, root: Path) -> DecisionPacket:
    mapping_path = root / "candidate-map.json"
    if (
        not root.is_dir()
        or stat.S_IMODE(root.stat().st_mode) != 0o700
        or not mapping_path.is_file()
        or stat.S_IMODE(mapping_path.stat().st_mode) != 0o600
    ):
        raise _fail("packet_permissions")
    mapping = load_strict_contract_json(mapping_path)
    if (
        mapping.get("protocol_hash") != decision.protocol_hash
        or mapping.get("repository_head") != decision.repository_harness_commit_sha
    ):
        raise _fail("packet_identity")
    candidate_map = mapping.get("candidate_map")
    expected_candidates = {item.candidate_id for item in decision.candidates}
    if (
        type(candidate_map) is not dict
        or set(candidate_map) != expected_candidates
        or set(candidate_map.values()) != {"B1", "B2", "B3", "B4"}
        or not (root / "results").is_dir()
        or stat.S_IMODE((root / "results").stat().st_mode) != 0o700
    ):
        raise _fail("packet_identity")
    return DecisionPacket(
        root=root,
        results_directory=root / "results",
        candidate_map=MappingProxyType(dict(candidate_map)),
    )


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _current_head(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "preflight",
            "authorization-text",
            "validate-authorization",
            "initialize",
            "execute",
            "inspect",
            "grade",
        ),
    )
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET_PATH)
    parser.add_argument("--authorization-file", type=Path)
    parser.add_argument("--second-grades-file", type=Path)
    arguments = parser.parse_args(argv)
    root = _repository_root()
    decision = build_capstone_text_decision(
        repository_root=root,
        repository_harness_commit_sha=_current_head(root),
    )
    if arguments.command == "preflight":
        print(json.dumps(decision.offline_preflight(), indent=2, sort_keys=True))
    elif arguments.command == "authorization-text":
        print(decision.expected_authorization_text())
    elif arguments.command == "validate-authorization":
        if arguments.authorization_file is None:
            parser.error("--authorization-file is required")
        authorization = _read_authorization(arguments.authorization_file)
        decision.validate_authorization_text(authorization)
        print(json.dumps({"status": "authorization_valid"}))
    elif arguments.command == "initialize":
        packet = decision.initialize_packet(arguments.packet)
        print(json.dumps({"status": "initialized", "packet": str(packet.root)}))
    elif arguments.command == "execute":
        if arguments.authorization_file is None:
            parser.error("--authorization-file is required for execute")
        authorization = _read_authorization(arguments.authorization_file)
        packet = _load_existing_packet(decision, arguments.packet)
        print(
            json.dumps(
                decision.execute(
                    authorization_text=authorization,
                    packet=packet,
                ),
                indent=2,
                sort_keys=True,
            )
        )
    elif arguments.command == "inspect":
        packet = _load_existing_packet(decision, arguments.packet)
        results = sorted(packet.results_directory.glob("decision-call-*.json"))
        safe = []
        for path in results:
            record = load_strict_contract_json(path)
            safe.append(
                {
                    "run_id": record["run_id"],
                    "blinded_candidate_id": record["blinded_candidate_id"],
                    "fixture_id": record["fixture_id"],
                    "result_status": record["result_status"],
                    "safe_failure_code": record["safe_failure_code"],
                    "latency_seconds": record["latency_seconds"],
                }
            )
        print(json.dumps({"packet": str(packet.root), "results": safe}, indent=2))
    else:
        packet = _load_existing_packet(decision, arguments.packet)
        print(
            json.dumps(
                decision.grade_packet(
                    packet,
                    secondary_grades_path=arguments.second_grades_file,
                ),
                indent=2,
                sort_keys=True,
            )
        )
    return 0


def _read_authorization(path: Path) -> str:
    if (
        not path.is_file()
        or stat.S_IMODE(path.stat().st_mode) != 0o600
        or path.stat().st_size > 16_384
    ):
        raise _fail("authorization_file")
    authorization = path.read_text(encoding="utf-8")
    if authorization.endswith("\n"):
        authorization = authorization[:-1]
    return authorization


if __name__ == "__main__":
    raise SystemExit(main())
