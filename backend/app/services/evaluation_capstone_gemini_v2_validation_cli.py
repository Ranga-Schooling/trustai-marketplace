"""Offline-first CLI for the corrected single-use Gemini/PT1 V2 observation.

Only ``execute --confirm-live`` can cross the Gemini provider boundary.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.services.evaluation_capstone_gemini_v2_validation import (
    CAPSTONE_GEMINI_V2_VALIDATION_STATUS,
    CapstoneLiveValidationError,
    build_capstone_gemini_v2_validation,
)
from app.services.evaluation_contract_identity import load_strict_contract_json
from app.services.evaluation_live_transport import (
    ConcreteLivePilotTransport,
    HttpxSender,
    LazyEnvironmentCredentialResolver,
    LiveTransportError,
)


_ROOT = Path(__file__).resolve().parents[3]


def _emit(value: Any) -> None:
    print(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=True)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("status")
    for name in ("dry-run", "authorization", "preflight", "execute", "inspect"):
        item = commands.add_parser(name)
        item.add_argument("--repository-head", required=True)
        item.add_argument("--case-id", required=True)
        if name in {"authorization", "preflight", "execute"}:
            if name == "authorization":
                item.add_argument("--authorized-at-utc", required=True)
                item.add_argument(
                    "--confirm-explicit-user-authorization",
                    action="store_true",
                )
            else:
                item.add_argument("--authorization", required=True)
        if name == "execute":
            item.add_argument("--confirm-live", action="store_true")
    return parser


def run_cli(
    argv: list[str] | None = None,
    *,
    repository_root: str | Path = _ROOT,
    operational_root: str | Path | None = None,
    environment_getter=None,
    sender_factory=HttpxSender,
    require_clean_repository: bool = True,
) -> int:
    options = _parser().parse_args(argv)
    if options.command is None:
        _emit({"status": "blocked", "reason": "command_required"})
        return 2
    try:
        if options.command == "status":
            _emit(
                {
                    "status": CAPSTONE_GEMINI_V2_VALIDATION_STATUS,
                    "execution": "blocked_awaiting_explicit_user_authorization",
                    "provider_calls": 0,
                    "credentials_accessed": 0,
                }
            )
            return 0
        if options.command == "execute" and not options.confirm_live:
            raise CapstoneLiveValidationError(
                "explicit_live_confirmation_required"
            )
        validator = build_capstone_gemini_v2_validation(
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
            validator.validate_historical_state(state_root)
            validator.validate_case_availability(options.case_id, state_root)
            runtime = ConcreteLivePilotTransport(sender_factory()).validate_runtime()
            _emit(
                validator.build_authorization_document(
                    case_id=options.case_id,
                    runtime_identity=runtime,
                    authorized_at_utc=options.authorized_at_utc,
                )
            )
            return 0
        if options.command == "preflight":
            authorization = load_strict_contract_json(options.authorization)
            binding, runtime, projection = validator.validate_offline_preflight(
                authorization_document=authorization,
                operational_root=state_root,
                transport=ConcreteLivePilotTransport(sender_factory()),
            )
            case = validator.case(binding.case_id)
            _emit(
                {
                    "status": "ready_for_one_explicitly_confirmed_live_call",
                    "validation_case_id": case.case_id,
                    "provider": case.provider,
                    "model": case.model,
                    "fixture_id": case.fixture_id,
                    "request_configuration_id": case.request_configuration_id,
                    "request_configuration_hash": case.request_configuration_hash,
                    "request_hash": case.request_hash,
                    "authorization_hash": binding.semantic_hash,
                    "contract_hash": validator.contract.semantic_hash,
                    "runtime_identity": runtime,
                    "runtime_identity_hash": binding.runtime_identity_hash,
                    "transport_projection": projection,
                    "conservative_reservation_usd": case.conservative_reservation_usd,
                    "cumulative_worst_case_validation_exposure_usd": (
                        case.cumulative_exposure_usd
                    ),
                    "validation_spend_remaining_after_reservation_usd": (
                        case.remaining_after_reservation_usd
                    ),
                    "maximum_provider_calls": 1,
                    "retry_count": 0,
                    "credentials_accessed": 0,
                    "provider_calls": 0,
                }
            )
            return 0
        if options.command == "inspect":
            _emit(validator.inspect_result(options.case_id, state_root))
            return 0
        authorization = load_strict_contract_json(options.authorization)
        if authorization.get("validation_case_id") != options.case_id:
            raise CapstoneLiveValidationError("validation_case_id")
        record = validator.execute_one(
            authorization_document=authorization,
            confirm_live=True,
            credential_resolver=LazyEnvironmentCredentialResolver(
                environment_getter
            ),
            transport=ConcreteLivePilotTransport(sender_factory()),
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
                "physical_provider_attempts": record[
                    "physical_provider_attempts"
                ],
                "retry_count": record["retry_count"],
                "record_hash": record["record_hash"],
            }
        )
        return 0 if record["result_status"] == "accepted" else 3
    except (CapstoneLiveValidationError, LiveTransportError) as exc:
        _emit({"status": "blocked", "reason": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(run_cli())
