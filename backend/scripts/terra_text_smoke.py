"""Prepare or execute one explicitly authorized Terra production-path smoke.

``describe`` and ``preflight`` are credential-free and perform no network I/O.
``execute`` is the sole live boundary and constrains ``GPTProvider`` to one
physical attempt.  This script is intentionally synthetic and does not write
to the application database or retain provider response content.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.schemas.schemas import AIAnalysisResult, ListingIn
from app.services.ai import (
    AnalysisFailure,
    GPTAnalysisObservation,
    GPTProvider,
    SYSTEM_PROMPT,
    build_openai_responses_payload,
)


SMOKE_ID = "terra-production-text-smoke-v2"
RESULT_CONTRACT_ID = "terra-production-text-smoke-result-v2"
RESULT_CONTRACT_VERSION = "v2"
RESULT_FILE = "result.json"
FIXTURE_ID = "terra-production-text-smoke-synthetic-v1"
REQUEST_CONFIGURATION_ID = "terra-production-responses-text-v1"
MODEL = "gpt-5.6-terra"
ENDPOINT = "https://api.openai.com/v1/responses"
ENDPOINT_IDENTITY = f"POST {ENDPOINT}"
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_INPUT_USD_PER_TOKEN = Decimal("0.000002")
_CACHED_INPUT_USD_PER_TOKEN = Decimal("0.0000002")
_OUTPUT_USD_PER_TOKEN = Decimal("0.000012")
_MONEY_QUANTUM = Decimal("0.00000001")
_STAGE_RESULTS = frozenset({"passed", "failed", "not_reached"})
_SAFE_FINISH_REASONS = frozenset(
    {
        "completed",
        "cost_ceiling_exceeded",
        "evidence_policy_failed",
        "http_error",
        "invalid_content_type",
        "parser_failed",
        "response_contract_failed",
        "result_unavailable",
        "schema_failed",
        "timeout",
        "transport_error",
        "usage_unavailable",
        "validator_failed",
    }
)
_EXPECTED_STAGES_BY_FINISH_REASON = {
    "completed": ("passed", "passed", "passed", "passed", "passed"),
    "cost_ceiling_exceeded": ("passed", "passed", "passed", "passed", "passed"),
    "evidence_policy_failed": ("passed", "passed", "passed", "failed", "passed"),
    "http_error": (
        "not_reached",
        "not_reached",
        "not_reached",
        "not_reached",
        "not_reached",
    ),
    "invalid_content_type": (
        "not_reached",
        "not_reached",
        "not_reached",
        "not_reached",
        "not_reached",
    ),
    "parser_failed": (
        "failed",
        "not_reached",
        "not_reached",
        "not_reached",
        "not_reached",
    ),
    "response_contract_failed": (
        "not_reached",
        "not_reached",
        "not_reached",
        "not_reached",
        "not_reached",
    ),
    "result_unavailable": ("passed", "passed", "passed", "passed", "passed"),
    "schema_failed": ("passed", "failed", "not_reached", "not_reached", "failed"),
    "timeout": (
        "not_reached",
        "not_reached",
        "not_reached",
        "not_reached",
        "not_reached",
    ),
    "transport_error": (
        "not_reached",
        "not_reached",
        "not_reached",
        "not_reached",
        "not_reached",
    ),
    "usage_unavailable": ("passed", "passed", "passed", "passed", "passed"),
    "validator_failed": ("passed", "passed", "failed", "not_reached", "passed"),
}

_FIXTURE = {
    "title": "Synthetic solid oak side table",
    "price": 45.0,
    "currency": "USD",
    "source": "Synthetic marketplace fixture",
    "description": (
        "Synthetic benign listing for a used side table in good condition, "
        "available for in-person inspection before protected payment."
    ),
    "url": None,
}


class SmokeAuthorizationError(ValueError):
    """The operator authorization does not exactly match the smoke identity."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _listing() -> ListingIn:
    return ListingIn(**_FIXTURE)


def build_smoke_request_bytes() -> bytes:
    """Return exact canonical bytes built by the production request builder."""
    return _canonical(build_openai_responses_payload(_listing(), MODEL))


def build_smoke_descriptor(repository_head: str) -> dict[str, Any]:
    """Bind the synthetic fixture, production request, and conservative cost."""
    if not _SHA1.fullmatch(repository_head):
        raise SmokeAuthorizationError("repository_head")
    request = build_openai_responses_payload(_listing(), MODEL)
    request_bytes = _canonical(request)
    fixture_hash = _hash(_canonical(_FIXTURE))
    prompt_hash = _hash(SYSTEM_PROMPT.encode("utf-8"))
    schema_hash = _hash(_canonical(request["text"]["format"]["schema"]))
    configuration = {
        "endpoint": ENDPOINT,
        "maximum_output_tokens": GPTProvider.MAXIMUM_OUTPUT_TOKENS,
        "maximum_physical_attempts": 1,
        "model": MODEL,
        "reasoning_effort": "medium",
        "retries": 0,
        "service_tier": "default",
        "store": False,
        "stream": False,
        "temperature": 1.0,
        "timeout_seconds": 30,
        "tools_enabled": False,
        "truncation": "disabled",
    }
    input_token_upper_bound = len(request_bytes)
    cost_ceiling = (
        Decimal(input_token_upper_bound) * _INPUT_USD_PER_TOKEN
        + Decimal(GPTProvider.MAXIMUM_OUTPUT_TOKENS) * _OUTPUT_USD_PER_TOKEN
    ).quantize(_MONEY_QUANTUM)
    return {
        "smoke_id": SMOKE_ID,
        "repository_head": repository_head,
        "provider": "OpenAI",
        "model": MODEL,
        "endpoint": ENDPOINT,
        "prompt_version": Settings.model_fields["prompt_version"].default,
        "prompt_hash": prompt_hash,
        "schema_hash": schema_hash,
        "request_configuration_id": REQUEST_CONFIGURATION_ID,
        "request_configuration_hash": _hash(_canonical(configuration)),
        "fixture_id": FIXTURE_ID,
        "fixture_hash": fixture_hash,
        "request_hash": _hash(request_bytes),
        "request_bytes": len(request_bytes),
        "input_token_upper_bound": input_token_upper_bound,
        "maximum_output_tokens": GPTProvider.MAXIMUM_OUTPUT_TOKENS,
        "maximum_physical_attempts": 1,
        "retries": 0,
        "timeout_seconds": 30,
        "store": False,
        "stream": False,
        "tools_enabled": False,
        "pricing_schedule": "openai_gpt_5_6_terra_standard_short_context_v1",
        "input_usd_per_token": format(_INPUT_USD_PER_TOKEN, "f"),
        "cached_input_usd_per_token": format(
            _CACHED_INPUT_USD_PER_TOKEN,
            "f",
        ),
        "output_usd_per_token": format(_OUTPUT_USD_PER_TOKEN, "f"),
        "cost_ceiling_usd": format(cost_ceiling, "f"),
    }


def validate_authorization(
    authorization: dict[str, Any],
    descriptor: dict[str, Any],
) -> None:
    expected = {
        **descriptor,
        "authorization_scope": "production_text_smoke",
        "authorized": True,
    }
    if authorization != expected:
        raise SmokeAuthorizationError("authorization_identity")


def _private_mode(
    path: Path,
    expected_mode: int,
    kind: str,
    *,
    directory: bool = False,
) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise SmokeAuthorizationError(kind) from exc
    if (
        stat.S_IMODE(metadata.st_mode) != expected_mode
        or metadata.st_uid != os.getuid()
        or (directory and not stat.S_ISDIR(metadata.st_mode))
        or (not directory and not stat.S_ISREG(metadata.st_mode))
    ):
        raise SmokeAuthorizationError(kind)


def _validate_packet_directory(packet_dir: Path) -> None:
    _private_mode(
        packet_dir,
        0o700,
        "packet_directory_permissions",
        directory=True,
    )


def initialize_packet(packet_dir: Path) -> None:
    """Create one empty private packet without authorizing an invocation."""
    try:
        packet_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
        packet_dir.chmod(0o700)
    except OSError as exc:
        raise SmokeAuthorizationError("packet_already_initialized") from exc
    _validate_packet_directory(packet_dir)


def claim_smoke_attempt(packet_dir: Path, descriptor: dict[str, Any]) -> None:
    """Atomically consume the authorization before the provider boundary."""
    _validate_packet_directory(packet_dir)
    marker = packet_dir / "attempt-started.json"
    payload = _canonical(
        {
            "smoke_id": descriptor["smoke_id"],
            "repository_head": descriptor["repository_head"],
            "request_hash": descriptor["request_hash"],
            "maximum_physical_attempts": 1,
            "retries": 0,
        }
    )
    try:
        descriptor_fd = os.open(
            marker,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor_fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise SmokeAuthorizationError("smoke_attempt_already_consumed") from exc
    _private_mode(marker, 0o600, "attempt_marker_permissions")


def _estimated_cost(
    usage: dict[str, int | None] | None,
) -> Decimal | None:
    if usage is None:
        return None
    if type(usage) is not dict:
        return None
    expected = {
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
    }
    if set(usage) != expected:
        return None
    input_tokens = usage["input_tokens"]
    output_tokens = usage["output_tokens"]
    cached_input_tokens = usage["cached_input_tokens"]
    reasoning_tokens = usage["reasoning_tokens"]
    if (
        type(input_tokens) is not int
        or input_tokens < 0
        or type(output_tokens) is not int
        or output_tokens < 0
        or (
            cached_input_tokens is not None
            and (
                type(cached_input_tokens) is not int
                or cached_input_tokens < 0
                or cached_input_tokens > input_tokens
            )
        )
        or (
            reasoning_tokens is not None
            and (
                type(reasoning_tokens) is not int
                or reasoning_tokens < 0
                or reasoning_tokens > output_tokens
            )
        )
    ):
        return None

    # When the optional cached counter is absent, charge every input token at
    # the higher uncached rate. Reasoning tokens are already a documented
    # subset of output_tokens and therefore are never charged a second time.
    cached = cached_input_tokens or 0
    uncached = input_tokens - cached
    return (
        Decimal(uncached) * _INPUT_USD_PER_TOKEN
        + Decimal(cached) * _CACHED_INPUT_USD_PER_TOKEN
        + Decimal(output_tokens) * _OUTPUT_USD_PER_TOKEN
    ).quantize(_MONEY_QUANTUM)


def build_result_record(
    descriptor: dict[str, Any],
    observation: GPTAnalysisObservation,
    result: AIAnalysisResult | None,
) -> dict[str, Any]:
    """Build the closed, content-free V2 result record."""
    estimated_cost = _estimated_cost(observation.provider_usage)
    accepted = (
        observation.safe_finish_reason == "completed"
        and observation.physical_provider_attempts == 1
        and observation.retry_count == 0
        and observation.http_status == 200
        and observation.provider_usage is not None
        and estimated_cost is not None
        and estimated_cost <= Decimal(descriptor["cost_ceiling_usd"])
        and observation.parser_result == "passed"
        and observation.schema_result == "passed"
        and observation.validator_result == "passed"
        and observation.evidence_policy_result == "passed"
        and observation.ai_analysis_result_mapping_result == "passed"
        and result is not None
    )
    finish_reason = observation.safe_finish_reason
    if finish_reason == "completed":
        if observation.provider_usage is None or estimated_cost is None:
            finish_reason = "usage_unavailable"
        elif estimated_cost > Decimal(descriptor["cost_ceiling_usd"]):
            finish_reason = "cost_ceiling_exceeded"
        elif result is None:
            finish_reason = "result_unavailable"

    record: dict[str, Any] = {
        "result_contract_id": RESULT_CONTRACT_ID,
        "result_contract_version": RESULT_CONTRACT_VERSION,
        "smoke_id": descriptor["smoke_id"],
        "repository_head": descriptor["repository_head"],
        "provider": descriptor["provider"],
        "model": descriptor["model"],
        "endpoint_identity": ENDPOINT_IDENTITY,
        "result_status": "accepted" if accepted else "rejected",
        "safe_finish_reason": finish_reason,
        "physical_provider_attempts": observation.physical_provider_attempts,
        "retry_count": observation.retry_count,
        "http_status": observation.http_status,
        "latency_seconds": observation.latency_seconds,
        "provider_usage": observation.provider_usage,
        "estimated_cost_usd": (
            format(estimated_cost, "f") if estimated_cost is not None else None
        ),
        "certified_cost_ceiling_usd": descriptor["cost_ceiling_usd"],
        "parser_result": observation.parser_result,
        "schema_result": observation.schema_result,
        "validator_result": observation.validator_result,
        "evidence_policy_result": observation.evidence_policy_result,
        "ai_analysis_result_mapping_result": (
            observation.ai_analysis_result_mapping_result
        ),
        "request_configuration_id": descriptor["request_configuration_id"],
        "fixture_id": descriptor["fixture_id"],
        "prompt_version": descriptor["prompt_version"],
        "request_hash": descriptor["request_hash"],
        "configuration_hash": descriptor["request_configuration_hash"],
        "prompt_hash": descriptor["prompt_hash"],
        "schema_hash": descriptor["schema_hash"],
        "fixture_hash": descriptor["fixture_hash"],
        "normalized_semantic_hash": (
            _hash(_canonical(result.model_dump(mode="json")))
            if result is not None
            else None
        ),
        "raw_response_hash": observation.raw_response_hash,
        "raw_provider_content_exposed": False,
        "repository_mutated": False,
    }
    record["record_hash"] = _hash(_canonical(record))
    return record


_RESULT_FIELDS = frozenset(
    {
        "result_contract_id",
        "result_contract_version",
        "smoke_id",
        "repository_head",
        "provider",
        "model",
        "endpoint_identity",
        "result_status",
        "safe_finish_reason",
        "physical_provider_attempts",
        "retry_count",
        "http_status",
        "latency_seconds",
        "provider_usage",
        "estimated_cost_usd",
        "certified_cost_ceiling_usd",
        "parser_result",
        "schema_result",
        "validator_result",
        "evidence_policy_result",
        "ai_analysis_result_mapping_result",
        "request_configuration_id",
        "fixture_id",
        "prompt_version",
        "request_hash",
        "configuration_hash",
        "prompt_hash",
        "schema_hash",
        "fixture_hash",
        "normalized_semantic_hash",
        "raw_response_hash",
        "raw_provider_content_exposed",
        "repository_mutated",
        "record_hash",
    }
)


def _validate_result_record(
    record: dict[str, Any],
    descriptor: dict[str, Any],
) -> None:
    if set(record) != _RESULT_FIELDS:
        raise SmokeAuthorizationError("result_fields")
    record_without_hash = {
        key: value for key, value in record.items() if key != "record_hash"
    }
    if (
        type(record["record_hash"]) is not str
        or not _SHA256.fullmatch(record["record_hash"])
        or record["record_hash"] != _hash(_canonical(record_without_hash))
    ):
        raise SmokeAuthorizationError("result_hash")

    identities = {
        "result_contract_id": RESULT_CONTRACT_ID,
        "result_contract_version": RESULT_CONTRACT_VERSION,
        "smoke_id": descriptor["smoke_id"],
        "repository_head": descriptor["repository_head"],
        "provider": descriptor["provider"],
        "model": descriptor["model"],
        "endpoint_identity": ENDPOINT_IDENTITY,
        "request_configuration_id": descriptor["request_configuration_id"],
        "fixture_id": descriptor["fixture_id"],
        "prompt_version": descriptor["prompt_version"],
        "request_hash": descriptor["request_hash"],
        "configuration_hash": descriptor["request_configuration_hash"],
        "prompt_hash": descriptor["prompt_hash"],
        "schema_hash": descriptor["schema_hash"],
        "fixture_hash": descriptor["fixture_hash"],
        "certified_cost_ceiling_usd": descriptor["cost_ceiling_usd"],
        "raw_provider_content_exposed": False,
        "repository_mutated": False,
    }
    if any(record[key] != value for key, value in identities.items()):
        raise SmokeAuthorizationError("result_identity")
    if (
        record["physical_provider_attempts"] != 1
        or type(record["physical_provider_attempts"]) is not int
        or record["retry_count"] != 0
        or type(record["retry_count"]) is not int
    ):
        raise SmokeAuthorizationError("result_attempts")
    if (
        type(record["safe_finish_reason"]) is not str
        or record["safe_finish_reason"] not in _SAFE_FINISH_REASONS
    ):
        raise SmokeAuthorizationError("result_finish_reason")
    latency = record["latency_seconds"]
    if (
        type(latency) not in (int, float)
        or not math.isfinite(latency)
        or latency < 0
    ):
        raise SmokeAuthorizationError("result_latency")
    http_status = record["http_status"]
    if http_status is not None and (
        type(http_status) is not int or not 100 <= http_status <= 599
    ):
        raise SmokeAuthorizationError("result_http_status")
    for stage in (
        "parser_result",
        "schema_result",
        "validator_result",
        "evidence_policy_result",
        "ai_analysis_result_mapping_result",
    ):
        if type(record[stage]) is not str or record[stage] not in _STAGE_RESULTS:
            raise SmokeAuthorizationError("result_stage")

    estimated_cost = _estimated_cost(record["provider_usage"])
    if record["provider_usage"] is not None and estimated_cost is None:
        raise SmokeAuthorizationError("result_usage")
    expected_cost = format(estimated_cost, "f") if estimated_cost is not None else None
    if record["estimated_cost_usd"] != expected_cost:
        raise SmokeAuthorizationError("result_cost")
    for field in ("raw_response_hash", "normalized_semantic_hash"):
        value = record[field]
        if value is not None and (
            type(value) is not str or not _SHA256.fullmatch(value)
        ):
            raise SmokeAuthorizationError("result_safe_hash")

    transport_failure = record["safe_finish_reason"] in {"timeout", "transport_error"}
    if transport_failure:
        if record["http_status"] is not None or record["raw_response_hash"] is not None:
            raise SmokeAuthorizationError("result_transport_evidence")
    elif record["raw_response_hash"] is None:
        raise SmokeAuthorizationError("result_response_hash")
    if record["safe_finish_reason"] == "http_error":
        if record["http_status"] in (None, 200):
            raise SmokeAuthorizationError("result_http_failure")
    elif not transport_failure and record["http_status"] != 200:
        raise SmokeAuthorizationError("result_http_success")

    if record["result_status"] == "accepted":
        if (
            record["safe_finish_reason"] != "completed"
            or record["http_status"] != 200
            or estimated_cost is None
            or estimated_cost > Decimal(descriptor["cost_ceiling_usd"])
            or any(
                record[stage] != "passed"
                for stage in (
                    "parser_result",
                    "schema_result",
                    "validator_result",
                    "evidence_policy_result",
                    "ai_analysis_result_mapping_result",
                )
            )
            or record["raw_response_hash"] is None
            or record["normalized_semantic_hash"] is None
        ):
            raise SmokeAuthorizationError("result_acceptance")
    elif record["result_status"] != "rejected":
        raise SmokeAuthorizationError("result_status")

    stage_tuple = (
        record["parser_result"],
        record["schema_result"],
        record["validator_result"],
        record["evidence_policy_result"],
        record["ai_analysis_result_mapping_result"],
    )
    if stage_tuple != _EXPECTED_STAGES_BY_FINISH_REASON[
        record["safe_finish_reason"]
    ]:
        raise SmokeAuthorizationError("result_stage_order")


def write_result_record(packet_dir: Path, record: dict[str, Any]) -> None:
    """Atomically retain one immutable private smoke result."""
    _validate_packet_directory(packet_dir)
    if type(record) is not dict or type(record.get("repository_head")) is not str:
        raise SmokeAuthorizationError("result_file")
    _validate_result_record(
        record,
        build_smoke_descriptor(record["repository_head"]),
    )
    result_path = packet_dir / RESULT_FILE
    temporary_path = packet_dir / ".result.json.tmp"
    payload = _canonical(record)
    try:
        temporary_fd = os.open(
            temporary_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(temporary_fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary_path, result_path)
        os.unlink(temporary_path)
        directory_fd = os.open(packet_dir, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise SmokeAuthorizationError("result_already_exists") from exc
    _private_mode(result_path, 0o600, "result_file_permissions")


def _load_closed_json(path: Path, kind: str) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_closed_object,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise SmokeAuthorizationError(kind) from exc
    if type(value) is not dict:
        raise SmokeAuthorizationError(kind)
    return value


def inspect_result(
    packet_dir: Path,
    descriptor: dict[str, Any],
) -> dict[str, Any]:
    """Validate and return only the closed safe result projection."""
    _validate_packet_directory(packet_dir)
    result_path = packet_dir / RESULT_FILE
    _private_mode(result_path, 0o600, "result_file_permissions")
    record = _load_closed_json(result_path, "result_file")
    _validate_result_record(record, descriptor)
    return record


def run_authorized_smoke(
    authorization: dict[str, Any],
    *,
    repository_head: str,
    provider_factory: Callable[..., GPTProvider] = GPTProvider,
) -> dict[str, Any]:
    """Cross the live boundary once after exact offline identity validation."""
    descriptor = build_smoke_descriptor(repository_head)
    validate_authorization(authorization, descriptor)
    observations: list[GPTAnalysisObservation] = []
    provider = provider_factory(
        maximum_attempts=1,
        observation_callback=observations.append,
    )
    if provider.model_name != MODEL:
        raise SmokeAuthorizationError("configured_model")
    if _hash(_canonical(provider.request_payload(_listing()))) != descriptor[
        "request_hash"
    ]:
        raise SmokeAuthorizationError("production_request_identity")
    result: AIAnalysisResult | None
    try:
        result, _ = provider.analyze(_listing())
    except AnalysisFailure:
        result = None
    if len(observations) != 1:
        raise SmokeAuthorizationError("terminal_observation")
    record = build_result_record(descriptor, observations[0], result)
    _validate_result_record(record, descriptor)
    return record


def _closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SmokeAuthorizationError("duplicate_authorization_key")
        result[key] = value
    return result


def _load_authorization(path: Path) -> dict[str, Any]:
    _private_mode(path, 0o600, "authorization_file_permissions")
    return _load_closed_json(path, "authorization_file")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=("describe", "initialize", "preflight", "execute", "inspect"),
    )
    parser.add_argument("--repository-head", required=True)
    parser.add_argument("--authorization-file", type=Path)
    parser.add_argument("--packet-dir", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    descriptor = build_smoke_descriptor(args.repository_head)
    if args.mode == "describe":
        print(json.dumps(descriptor, indent=2, sort_keys=True))
        return 0
    if args.mode == "initialize":
        if args.packet_dir is None:
            raise SmokeAuthorizationError("packet_dir_required")
        if args.authorization_file is not None:
            raise SmokeAuthorizationError("authorization_not_permitted")
        initialize_packet(args.packet_dir)
        print(
            json.dumps(
                {
                    "smoke_id": SMOKE_ID,
                    "status": "initialized_not_authorized",
                    "credential_accessed": False,
                    "provider_calls": 0,
                },
                sort_keys=True,
            )
        )
        return 0
    if args.mode == "inspect":
        if args.packet_dir is None:
            raise SmokeAuthorizationError("packet_dir_required")
        if args.authorization_file is not None:
            raise SmokeAuthorizationError("authorization_not_permitted")
        print(json.dumps(inspect_result(args.packet_dir, descriptor), sort_keys=True))
        return 0
    if args.packet_dir is None:
        raise SmokeAuthorizationError("packet_dir_required")
    if args.authorization_file is None:
        raise SmokeAuthorizationError("authorization_file_required")
    _validate_packet_directory(args.packet_dir)
    if args.authorization_file != args.packet_dir / "authorization.json":
        raise SmokeAuthorizationError("authorization_file_location")
    authorization = _load_authorization(args.authorization_file)
    validate_authorization(authorization, descriptor)
    if args.mode == "preflight":
        if (
            (args.packet_dir / "attempt-started.json").exists()
            or (args.packet_dir / RESULT_FILE).exists()
        ):
            raise SmokeAuthorizationError("smoke_attempt_already_consumed")
        print(
            json.dumps(
                {
                    "smoke_id": SMOKE_ID,
                    "status": "ready_for_one_authorized_invocation",
                    "request_hash": descriptor["request_hash"],
                    "maximum_physical_attempts": 1,
                    "retries": 0,
                    "credential_accessed": False,
                    "provider_calls": 0,
                },
                sort_keys=True,
            )
        )
        return 0
    claim_smoke_attempt(args.packet_dir, descriptor)
    record = run_authorized_smoke(
        authorization,
        repository_head=args.repository_head,
    )
    write_result_record(args.packet_dir, record)
    print(json.dumps(record, sort_keys=True))
    return 0 if record["result_status"] == "accepted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
