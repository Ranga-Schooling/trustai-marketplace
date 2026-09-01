# Capstone live validation

Capstone live validation is a bounded integration check. It is not the strict
research pilot, scored evaluation, winner selection, or production deployment.
The strict pilot remains fail-closed while its OpenAI token-count operation is
`pending_cost_reconciliation`. A Capstone result cannot be promoted into a
pilot or scored result.

Version 1 contains one case: the frozen OpenAI Terra/PT1 text request derived
from strict plan `call-0003`. Its request hash is
`97f8752bb33994a00018a15ff62d79419069397b223cc5f60770def973ebc266`.
The known input count is 1,018 tokens, its conservative reservation is
USD 0.05169700, and the independent Capstone ceiling is USD 1.00000000.
The fixed local reservation marker makes this version a one-call procedure.

Terra/PT1 comes first because it is the only current text case with an exact
frozen request, observed input-token count, conservative sub-USD-1 reservation,
confirmed endpoint permission, and externally bounded prepaid exposure. PT2
may be considered only after PT1 succeeds. Sol and Gemini require a separately
reviewed case addition. Groq text remains deferred because the supplied 8,000
TPM limit cannot be defended against the frozen maximum request without
inventing tokenizer or provider-accounting semantics.

## Offline checks

Run these from `backend` using the repository's configured Python environment
with `requirements.txt` installed. They do not read credentials or make network
calls. Preflight fails before authorization can be consumed when the required
HTTP client runtime is unavailable.

```sh
CAPSTONE_HEAD=$(git rev-parse HEAD)

python -m app.services.evaluation_capstone_live_validation_cli status

python -m app.services.evaluation_capstone_live_validation_cli dry-run \
  --repository-head "$CAPSTONE_HEAD" \
  --case-id capval-openai-terra-pt1-v1
```

The dry run must report `offline_dry_run_passed`, the exact request and
configuration hashes, zero credential access, and zero provider calls.

## One explicitly authorized call

Before preparing an authorization record, the user must provide an explicit
instruction binding all of the following:

> I explicitly authorize exactly one `capstone_live_validation` provider
> invocation at repository HEAD
> `<CURRENT_COMMITTED_HEAD_SHA>` for validation case
> `capval-openai-terra-pt1-v1`, source call `call-0003`, candidate
> `openai_unified_balanced_v1`, provider `OpenAI`, model `gpt-5.6-terra`,
> fixture `PT1`, workload `text_analysis`, request configuration
> `openai_terra_text_pilot_v1` with hash
> `0eca58d264b7af9e48af182f8d3ce8a0a417db8201328b70fdab77b6a4bae893`,
> request hash
> `97f8752bb33994a00018a15ff62d79419069397b223cc5f60770def973ebc266`,
> Capstone contract hash
> `389c8e4c693fc9bcff353f9704c104f8ec64ba98de05c3a6d9c0cd7e6eec7564`,
> maximum calls `1`, retries `0`, total Capstone ceiling USD `1.00000000`,
> and conservative reservation USD `0.05169700`. The strict pending-cost
> reconciliation remains unchanged. Strict-pilot execution, scored execution,
> winner selection, and production deployment are not authorized.

Only after that authorization is present, create its hash-bound local record.
Replace the timestamp placeholder with the authorization time in canonical UTC
seconds:

```sh
python -m app.services.evaluation_capstone_live_validation_cli authorization \
  --repository-head "$CAPSTONE_HEAD" \
  --case-id capval-openai-terra-pt1-v1 \
  --authorized-at-utc 2026-09-01T00:00:00Z \
  --confirm-explicit-user-authorization \
  > /tmp/capval-openai-terra-pt1-v1.authorization.json

python -m app.services.evaluation_capstone_live_validation_cli preflight \
  --repository-head "$CAPSTONE_HEAD" \
  --authorization /tmp/capval-openai-terra-pt1-v1.authorization.json
```

Both commands are offline. The following is the only command in this workflow
that can make a real provider call; do not run it without the explicit human
authorization above and a privately provisioned runtime `OPENAI_API_KEY`:

```sh
python -m app.services.evaluation_capstone_live_validation_cli execute \
  --repository-head "$CAPSTONE_HEAD" \
  --case-id capval-openai-terra-pt1-v1 \
  --authorization /tmp/capval-openai-terra-pt1-v1.authorization.json \
  --confirm-live
```

The command creates an ignored, mode-0600 reservation marker immediately
before transport, performs at most one invocation with redirects disabled and
no retry, writes a safe result, and stops. An existing reservation marker
blocks replay even when a prior invocation failed or the process was
interrupted.

## Safe inspection and credential revocation

Inspection is offline and does not expose raw provider prose:

```sh
python -m app.services.evaluation_capstone_live_validation_cli inspect \
  --repository-head "$CAPSTONE_HEAD"
```

After the observation, remove the runtime variable from the shell without
printing it:

```sh
unset OPENAI_API_KEY
```

Disable or delete the dedicated key in the provider project when it is no
longer needed. Do not place credentials in Git, fixtures, authorizations,
result records, logs, or shell arguments.
