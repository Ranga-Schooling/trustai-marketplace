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
import re
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.schemas.schemas import ListingIn
from app.services.ai import (
    GPTProvider,
    SYSTEM_PROMPT,
    build_openai_responses_payload,
)


SMOKE_ID = "terra-production-text-smoke-v1"
FIXTURE_ID = "terra-production-text-smoke-synthetic-v1"
REQUEST_CONFIGURATION_ID = "terra-production-responses-text-v1"
MODEL = "gpt-5.6-terra"
ENDPOINT = "https://api.openai.com/v1/responses"
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_INPUT_USD_PER_TOKEN = Decimal("0.000002")
_OUTPUT_USD_PER_TOKEN = Decimal("0.000012")
_MONEY_QUANTUM = Decimal("0.00000001")

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


def claim_smoke_attempt(packet_dir: Path, descriptor: dict[str, Any]) -> None:
    """Atomically consume the authorization before the provider boundary."""
    try:
        packet_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
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
        with marker.open("xb") as stream:
            stream.write(payload)
    except OSError as exc:
        raise SmokeAuthorizationError("smoke_attempt_already_consumed") from exc


def run_authorized_smoke(
    authorization: dict[str, Any],
    *,
    repository_head: str,
    provider_factory: Callable[..., GPTProvider] = GPTProvider,
) -> dict[str, Any]:
    """Cross the live boundary once after exact offline identity validation."""
    descriptor = build_smoke_descriptor(repository_head)
    validate_authorization(authorization, descriptor)
    provider = provider_factory(maximum_attempts=1)
    if provider.model_name != MODEL:
        raise SmokeAuthorizationError("configured_model")
    if _hash(_canonical(provider.request_payload(_listing()))) != descriptor[
        "request_hash"
    ]:
        raise SmokeAuthorizationError("production_request_identity")
    result, raw_response = provider.analyze(_listing())
    normalized = result.model_dump(mode="json")
    return {
        "smoke_id": SMOKE_ID,
        "repository_head": repository_head,
        "provider": "OpenAI",
        "model": provider.model_name,
        "result_status": "accepted",
        "physical_attempts": 1,
        "retries": 0,
        "request_hash": descriptor["request_hash"],
        "provider_response_hash": _hash(raw_response.encode("utf-8")),
        "normalized_result_hash": _hash(_canonical(normalized)),
        "raw_response_retained": False,
        "database_write_performed": False,
    }


def _closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SmokeAuthorizationError("duplicate_authorization_key")
        result[key] = value
    return result


def _load_authorization(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_closed_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SmokeAuthorizationError("authorization_file") from exc
    if type(value) is not dict:
        raise SmokeAuthorizationError("authorization_file")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("describe", "preflight", "execute"))
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
    if args.authorization_file is None:
        raise SmokeAuthorizationError("authorization_file_required")
    authorization = _load_authorization(args.authorization_file)
    validate_authorization(authorization, descriptor)
    if args.mode == "preflight":
        if args.packet_dir is None:
            raise SmokeAuthorizationError("packet_dir_required")
        if (args.packet_dir / "attempt-started.json").exists():
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
    if args.packet_dir is None:
        raise SmokeAuthorizationError("packet_dir_required")
    claim_smoke_attempt(args.packet_dir, descriptor)
    print(
        json.dumps(
            run_authorized_smoke(
                authorization,
                repository_head=args.repository_head,
            ),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
