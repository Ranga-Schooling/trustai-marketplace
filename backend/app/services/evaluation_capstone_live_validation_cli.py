"""Operator CLI for one bounded Capstone live-validation observation.

Status, dry-run, authorization preparation, preflight, and inspection are
offline.  Only ``execute --confirm-live`` can cross the provider boundary.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
import json
from pathlib import Path
from typing import Any

from app.services.evaluation_capstone_live_validation import (
    CAPSTONE_LIVE_VALIDATION_STATUS,
    CapstoneLiveValidationError,
    build_capstone_live_validation,
)
from app.services.evaluation_contract_identity import load_strict_contract_json
from app.services.evaluation_live_transport import (
    ConcreteLivePilotTransport,
    HttpxSender,
    LazyEnvironmentCredentialResolver,
    LiveTransportError,
)


_ROOT = Path(__file__).resolve().parents[3]
_STATUS = {
    "status": CAPSTONE_LIVE_VALIDATION_STATUS,
    "execution_class": "capstone_live_validation",
    "execution": "blocked_awaiting_explicit_user_authorization",
    "provider_calls": 0,
    "strict_pilot_calls": 0,
    "scored_calls": 0,
    "credentials_accessed": 0,
    "winner_selected": False,
}


def _emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=True)
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("status")
    dry_run = subparsers.add_parser("dry-run")
    dry_run.add_argument("--repository-head", required=True)
    dry_run.add_argument("--case-id", required=True)
    authorization = subparsers.add_parser("authorization")
    authorization.add_argument("--repository-head", required=True)
    authorization.add_argument("--case-id", required=True)
    authorization.add_argument("--authorized-at-utc", required=True)
    authorization.add_argument(
        "--confirm-explicit-user-authorization",
        action="store_true",
    )
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--repository-head", required=True)
    preflight.add_argument("--authorization", required=True)
    execute = subparsers.add_parser("execute")
    execute.add_argument("--repository-head", required=True)
    execute.add_argument("--case-id", required=True)
    execute.add_argument("--authorization", required=True)
    execute.add_argument("--confirm-live", action="store_true")
    inspect = subparsers.add_parser("inspect")
    inspect.add_argument("--repository-head", required=True)
    return parser


def run_cli(
    argv: list[str] | None = None,
    *,
    repository_root: str | Path = _ROOT,
    operational_root: str | Path | None = None,
    environment_getter: Callable[[str], str | None] | None = None,
    sender_factory: Callable[[], Any] = HttpxSender,
    require_clean_repository: bool = True,
) -> int:
    """Run one command; no non-execute command resolves credentials."""
    arguments = list(argv or [])
    if not arguments:
        _emit(_STATUS)
        return 0
    try:
        options = _parser().parse_args(arguments)
    except SystemExit:
        _emit({"status": "blocked", "reason": "invalid_arguments"})
        return 2
    if options.command == "status":
        _emit(_STATUS)
        return 0
    if options.command == "execute" and not options.confirm_live:
        _emit({"status": "blocked", "reason": "explicit_live_confirmation_required"})
        return 2
    try:
        validator = build_capstone_live_validation(
            repository_root=repository_root,
            repository_head=options.repository_head,
            require_clean_repository=require_clean_repository,
        )
        state_root = (
            Path(operational_root)
            if operational_root is not None
            else Path(repository_root) / ".capstone-live-validation"
        )
        if options.command == "dry-run":
            _emit(
                validator.dry_run(
                    options.case_id,
                    operational_root=state_root,
                    transport=ConcreteLivePilotTransport(sender_factory()),
                )
            )
            return 0
        if options.command == "authorization":
            if not options.confirm_explicit_user_authorization:
                raise CapstoneLiveValidationError(
                    "explicit_user_authorization_confirmation_required"
                )
            case = validator.case(options.case_id)
            validator.build_request(case.case_id)
            validator.validate_predecessor_state(state_root)
            validator.validate_case_availability(case.case_id, state_root)
            runtime_identity = ConcreteLivePilotTransport(
                sender_factory()
            ).validate_runtime()
            _emit(
                validator.build_authorization_document(
                    case_id=options.case_id,
                    runtime_identity=runtime_identity,
                    authorized_at_utc=options.authorized_at_utc,
                )
            )
            return 0
        if options.command == "preflight":
            authorization = load_strict_contract_json(options.authorization)
            binding, runtime_identity, transport_projection = (
                validator.validate_offline_preflight(
                    authorization_document=authorization,
                    operational_root=state_root,
                    transport=ConcreteLivePilotTransport(sender_factory()),
                )
            )
            case = validator.case(binding.case_id)
            _emit(
                {
                    "status": "ready_for_one_explicitly_confirmed_live_call",
                    "execution_class": binding.execution_class,
                    "validation_case_id": binding.case_id,
                    "authorization_hash": binding.semantic_hash,
                    "request_hash": case.request_hash,
                    "candidate_id": case.candidate_id,
                    "provider": case.provider,
                    "model": case.model,
                    "fixture_id": case.fixture_id,
                    "workload_stage": case.workload_stage,
                    "request_configuration_id": case.request_configuration_id,
                    "request_configuration_hash": (
                        case.request_configuration_hash
                    ),
                    "transport_projection": transport_projection,
                    "predecessor_validation_case_id": case.predecessor_case_id,
                    "predecessor_result_record_hash": (
                        case.predecessor_result_record_hash
                    ),
                    "predecessor_unresolved_exposure_usd": (
                        validator.contract.predecessor_unresolved_exposure_usd
                    ),
                    "runtime_identity": runtime_identity,
                    "runtime_identity_hash": binding.runtime_identity_hash,
                    "maximum_provider_calls": binding.maximum_provider_calls,
                    "retry_count": binding.retry_count,
                    "conservative_reservation_usd": (
                        case.conservative_reservation_usd
                    ),
                    "cumulative_worst_case_validation_exposure_usd": (
                        case.cumulative_exposure_usd
                    ),
                    "validation_spend_remaining_after_reservation_usd": (
                        case.remaining_after_reservation_usd
                    ),
                    "credentials_accessed": 0,
                    "provider_calls": 0,
                }
            )
            return 0
        if options.command == "inspect":
            _emit(validator.inspect_result(state_root))
            return 0
        if options.command != "execute":
            raise CapstoneLiveValidationError("invalid_command")
        authorization = load_strict_contract_json(options.authorization)
        if authorization.get("validation_case_id") != options.case_id:
            raise CapstoneLiveValidationError("validation_case_id")
        resolver = LazyEnvironmentCredentialResolver(environment_getter)
        transport = ConcreteLivePilotTransport(sender_factory())
        record = validator.execute_one(
            authorization_document=authorization,
            confirm_live=True,
            credential_resolver=resolver,
            transport=transport,
            operational_root=state_root,
        )
        _emit(
            {
                "status": "one_provider_call_completed_then_stopped",
                "validation_case_id": record["validation_case_id"],
                "result_status": record["result_status"],
                "safe_failure_classification": record[
                    "safe_failure_classification"
                ],
                "physical_provider_attempts": record["physical_provider_attempts"],
                "retry_count": record["retry_count"],
                "record_hash": record["record_hash"],
            }
        )
        return 0 if record["result_status"] == "accepted" else 3
    except (CapstoneLiveValidationError, LiveTransportError) as exc:
        _emit({"status": "blocked", "reason": str(exc)})
        return 2
    except (OSError, TypeError, ValueError):
        _emit({"status": "blocked", "reason": "capstone_validation_preflight_failed"})
        return 2


def main() -> int:
    import sys

    return run_cli(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
