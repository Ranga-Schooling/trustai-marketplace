"""Minimal fail-closed local operator entrypoint for the frozen pilot.

No-argument, status, help, presence, and preflight paths perform no network
operation.  Live execution requires an explicit mode, confirmation, immutable
same-day certification, external human authorization, exact reservations, and
lazy credentials.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from app.services.evaluation_contract_identity import load_strict_contract_json
from app.services.evaluation_live_gate import (
    LiveBoundaryGateError,
    build_live_gate_binding,
    load_same_day_certification,
)
from app.services.evaluation_live_transport import (
    ConcreteLivePilotTransport,
    HttpxSender,
    LazyEnvironmentCredentialResolver,
    credential_presence_lines,
)
from app.services.evaluation_pilot_budget import empty_pilot_budget_ledger
from app.services.evaluation_pilot_runner import (
    PilotRunnerError,
    build_provider_free_pilot_runner,
)


_ROOT = Path(__file__).resolve().parents[3]
_STATUS = {
    "status": "PILOT_LIVE_BOUNDARY_READY_AWAITING_USER",
    "execution": "blocked",
    "provider_calls": 0,
    "pilot_calls": 0,
    "scored_calls": 0,
    "credentials_accessed": 0,
}


def _emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("status", add_help=False)
    subparsers.add_parser("credential-presence", add_help=False)
    dry_run = subparsers.add_parser("dry-run", add_help=False)
    dry_run.add_argument("--call-id", required=True)
    preflight = subparsers.add_parser("preflight", add_help=False)
    preflight.add_argument("--certification", required=True)
    preflight.add_argument("--repository-head", required=True)
    execute = subparsers.add_parser("execute", add_help=False)
    execute.add_argument(
        "--mode",
        choices=("first-attempt-only", "full-authorized-pilot"),
        required=True,
    )
    execute.add_argument("--confirm-live", action="store_true")
    execute.add_argument("--certification")
    execute.add_argument("--authorization")
    execute.add_argument("--reservations")
    execute.add_argument("--repository-head")
    execute.add_argument("--call-id")
    return parser


def run_cli(
    argv: list[str] | None = None,
    *,
    environment_getter: Callable[[str], str | None] | None = None,
    repository_root: str | Path = _ROOT,
    sender_factory: Callable[[], Any] = HttpxSender,
    utc_date_getter: Callable[[], str] | None = None,
) -> int:
    """Run one safe command and return a process-style status code."""
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
    if options.command == "credential-presence":
        for line in credential_presence_lines(environment_getter):
            print(line)
        return 0
    today = (
        utc_date_getter()
        if utc_date_getter is not None
        else datetime.now(UTC).date().isoformat()
    )
    if options.command in {"dry-run", "preflight"}:
        try:
            repository_head = (
                options.repository_head
                if options.command == "preflight"
                else "0" * 40
            )
            runner = build_provider_free_pilot_runner(
                repository_root=repository_root,
                repository_harness_commit_sha=repository_head,
            )
            if options.command == "preflight":
                certification = load_same_day_certification(
                    options.certification,
                    current_date=today,
                )
                _emit(
                    {
                        "status": "ready_awaiting_private_user_gates",
                        "certification_hash": certification.semantic_hash,
                        "logical_runs": len(runner.plan.logical_runs),
                        "nominal_provider_calls": len(runner.plan.provider_calls),
                        "maximum_physical_attempts": runner.plan.maximum_real_physical_attempts,
                        "credentials_accessed": 0,
                        "provider_calls": 0,
                    }
                )
                return 0
            matches = tuple(
                call for call in runner.plan.provider_calls if call.call_id == options.call_id
            )
            if len(matches) != 1:
                raise PilotRunnerError("call_id")
            request = runner.build_native_request(matches[0])
            _emit(
                {
                    "status": "dry_run_only",
                    "call": matches[0].safe_projection(),
                    "request_payload_hash": request.payload_hash,
                    "request_body_bytes": len(request.payload_json),
                    "credentials_accessed": 0,
                    "provider_calls": 0,
                }
            )
            return 0
        except (LiveBoundaryGateError, PilotRunnerError) as exc:
            _emit({"status": "blocked", "reason": str(exc)})
            return 2
        except (OSError, TypeError, ValueError):
            _emit({"status": "blocked", "reason": "offline_preflight_failed"})
            return 2
    if options.command != "execute":
        _emit({"status": "blocked", "reason": "invalid_command"})
        return 2
    if options.mode == "first-attempt-only" and not options.call_id:
        _emit({"status": "blocked", "reason": "explicit_call_id_required"})
        return 2
    if options.mode == "full-authorized-pilot" and options.call_id is not None:
        _emit({"status": "blocked", "reason": "call_id_not_allowed_for_full_pilot"})
        return 2
    if not options.confirm_live:
        _emit({"status": "blocked", "reason": "explicit_live_confirmation_required"})
        return 2
    if not all(
        (
            options.certification,
            options.authorization,
            options.reservations,
            options.repository_head,
        )
    ):
        _emit({"status": "blocked", "reason": "live_bindings_required"})
        return 2
    try:
        runner = build_provider_free_pilot_runner(
            repository_root=repository_root,
            repository_harness_commit_sha=options.repository_head,
        )
        certification = load_same_day_certification(
            options.certification,
            current_date=today,
        )
        authorization = load_strict_contract_json(options.authorization)
        reservations = load_strict_contract_json(options.reservations)
        gate = build_live_gate_binding(
            runner=runner,
            certification=certification,
            authorization_document=authorization,
            current_date=today,
        )
        if type(reservations) is not dict or set(reservations) != set(gate.authorized_call_ids):
            raise LiveBoundaryGateError("reservation_inventory")
        resolver = LazyEnvironmentCredentialResolver(environment_getter)
        transport = ConcreteLivePilotTransport(sender_factory())
        ledger = empty_pilot_budget_ledger()
        if options.mode == "first-attempt-only":
            if gate.authorization_scope != "first_attempt_only":
                raise LiveBoundaryGateError("authorization_scope")
            call = next(
                item
                for item in runner.plan.provider_calls
                if item.call_id == options.call_id
            )
            if call.call_id != gate.authorized_call_ids[0]:
                raise LiveBoundaryGateError("authorized_call_id")
            outcome = runner.execute_one(
                call,
                gate=gate,
                credential_resolver=resolver,
                transport=transport,
                budget_ledger=ledger,
                conservative_reservation_usd=reservations[call.call_id],
                synthetic_today=today,
            )
            pending = bool(outcome.budget_ledger.unresolved_pending_attempts)
            _emit(
                {
                    "status": (
                        "BLOCKED_PENDING_COST_RECONCILIATION"
                        if pending
                        else "first_attempt_completed"
                        if outcome.accepted
                        else "stopped"
                    ),
                    "call_id": call.call_id,
                    "accepted": outcome.accepted,
                    "safe_failure_code": outcome.safe_failure_code,
                    **(
                        {
                            "billing_state": outcome.billing_state,
                            "pending_attempt_ids": list(
                                outcome.budget_ledger.unresolved_pending_attempt_ids
                            ),
                            "pending_encumbered_cost_usd": str(
                                outcome.budget_ledger.pending_encumbered_cost_usd
                            ),
                        }
                        if pending
                        else {}
                    ),
                    "physical_http_invocations": transport.invocation_count,
                    "committed_cost_usd": str(
                        outcome.budget_ledger.committed_cost_usd
                    ),
                    "remaining_budget_usd": str(
                        outcome.budget_ledger.remaining_unreserved_usd
                    ),
                }
            )
            return 0 if outcome.accepted and not pending else 3
        if gate.authorization_scope != "full_authorized_pilot":
            raise LiveBoundaryGateError("authorization_scope")
        completed = 0
        for logical_run in runner.plan.logical_runs:
            if logical_run.provider_free_no_call:
                runner.execute_pf1()
                completed += 1
                continue
            outcome = runner.execute_logical_run(
                logical_run,
                gate=gate,
                credential_resolver=resolver,
                transport=transport,
                budget_ledger=ledger,
                conservative_reservation_usd=reservations,
                synthetic_today=today,
            )
            ledger = outcome.budget_ledger
            if not outcome.accepted:
                pending = bool(ledger.unresolved_pending_attempts)
                _emit(
                    {
                        "status": (
                            "BLOCKED_PENDING_COST_RECONCILIATION"
                            if pending
                            else "stopped"
                        ),
                        "logical_run_id": logical_run.logical_run_id,
                        "completed_logical_runs": completed,
                        "physical_http_invocations": transport.invocation_count,
                        **(
                            {
                                "pending_attempt_ids": list(
                                    ledger.unresolved_pending_attempt_ids
                                ),
                                "pending_encumbered_cost_usd": str(
                                    ledger.pending_encumbered_cost_usd
                                ),
                            }
                            if pending
                            else {}
                        ),
                    }
                )
                return 3
            completed += 1
        _emit(
            {
                "status": "authorized_pilot_completed",
                "completed_logical_runs": completed,
                "physical_http_invocations": transport.invocation_count,
                "committed_cost_usd": str(ledger.committed_cost_usd),
                "remaining_budget_usd": str(ledger.remaining_unreserved_usd),
            }
        )
        return 0
    except (LiveBoundaryGateError, PilotRunnerError) as exc:
        _emit({"status": "blocked", "reason": str(exc)})
        return 2
    except (OSError, TypeError, ValueError):
        _emit({"status": "blocked", "reason": "live_preflight_failed"})
        return 2


def main() -> int:
    import sys

    return run_cli(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
