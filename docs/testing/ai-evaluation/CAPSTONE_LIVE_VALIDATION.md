# Capstone live validation

Capstone live validation is a bounded integration check. It is not the strict
research pilot, scored evaluation, winner selection, or production deployment.
The strict pilot remains fail-closed while its OpenAI token-count operation is
`pending_cost_reconciliation`. A Capstone result cannot be promoted into a
pilot or scored result.

## V1 history and V2 financial boundary

Version 1 case `capval-openai-terra-pt1-v1` is permanently consumed. Its safe
result hash is
`554fdf1685a4b766698d9af255fd7921e3500a7390915957831eab440582d24e`,
its actual provider cost is unresolved, and its USD `0.05169700` reservation
remains part of the independent Capstone exposure. V1 state must not be
deleted, reset, rewritten, or reused.

Version 2 contains one new case: `capval-openai-terra-pt1-v2`. It rebuilds the
same OpenAI Terra/PT1 request from strict plan `call-0003`; the request hash
must remain
`97f8752bb33994a00018a15ff62d79419069397b223cc5f60770def973ebc266`.
The model, fixture, prompt, configuration, schema, candidate, and model-visible
request are unchanged. V2 uses the corrected transport binding
`capstone_openai_httpx_transport_after_f420af3_v1` and a separate immutable
state directory.

The known input count is 1,018 tokens and the V2 reservation is USD
`0.05169700`. Exact Decimal carry-forward is:

```text
V1 unresolved exposure       0.05169700
V2 reservation             + 0.05169700
                            ------------
Cumulative exposure          0.10339400
Independent ceiling          1.00000000
Remaining ceiling          - 0.10339400
                            ------------
Remaining                    0.89660600
```

No V1 cost is inferred to be zero and the strict pilot budget is neither a
source nor a sink for this procedure.

## One dependency-complete runtime

Set `CAPSTONE_PYTHON` to one repository-supported Python environment in which
`backend/requirements.txt` is installed. Use that exact variable unchanged for
dry run, authorization construction, preflight, execution, and inspection.
The commands bind the Python executable/version and HTTPX version into the
authorization. A different runtime, HTTPX below `0.27`, a missing HTTPX
dependency, or an already consumed V2 case fails closed before credential
resolution or a provider invocation.

From the evaluation worktree's `backend` directory, require the operator to
select that dependency-complete interpreter explicitly:

```sh
: "${CAPSTONE_PYTHON:?Set CAPSTONE_PYTHON to the dependency-complete TrustAI backend Python}"
CAPSTONE_HEAD=$(git rev-parse HEAD)
```

Do not use the dependency-incomplete Homebrew Python. Do not install packages
globally merely to run this procedure.

## Offline checks

These commands do not read credentials or make network calls:

```sh
"$CAPSTONE_PYTHON" -m app.services.evaluation_capstone_live_validation_cli status

"$CAPSTONE_PYTHON" -m app.services.evaluation_capstone_live_validation_cli dry-run \
  --repository-head "$CAPSTONE_HEAD" \
  --case-id capval-openai-terra-pt1-v2
```

The dry run must report `offline_dry_run_passed`, the exact request and
configuration hashes, the V1 predecessor record hash and unresolved exposure,
the V2/cumulative/remaining amounts, the dependency-complete runtime identity,
zero credential access, and zero provider calls.

## One explicitly authorized V2 call

Before constructing an authorization record, the user must provide this exact
authorization with `<CURRENT_COMMITTED_HEAD_SHA>` replaced by the current
committed HEAD:

> I explicitly authorize exactly one `capstone_live_validation` provider
> invocation at repository HEAD `<CURRENT_COMMITTED_HEAD_SHA>` for validation
> case `capval-openai-terra-pt1-v2`, predecessor case
> `capval-openai-terra-pt1-v1`, predecessor reservation record hash
> `a9d604c30f16ecd4525d533955f9701ea15ed78c35cb7fff703c3e3761cd1bab`,
> predecessor result record hash
> `554fdf1685a4b766698d9af255fd7921e3500a7390915957831eab440582d24e`,
> and predecessor unresolved exposure USD `0.05169700`; source call
> `call-0003`, candidate `openai_unified_balanced_v1`, provider `OpenAI`, model
> `gpt-5.6-terra`, fixture `PT1`, workload `text_analysis`, request
> configuration `openai_terra_text_pilot_v1` with hash
> `0eca58d264b7af9e48af182f8d3ce8a0a417db8201328b70fdab77b6a4bae893`,
> request hash
> `97f8752bb33994a00018a15ff62d79419069397b223cc5f60770def973ebc266`,
> transport binding `capstone_openai_httpx_transport_after_f420af3_v1` with
> implementation hash
> `58dfb5ed2c3dc7ef51c24c88d53019fb8f4a3e06a528c8cc8d8af1790f66c218`,
> and Capstone V2 contract hash
> `48831c6dfafcdd00ab7e8a525d448574526ffefbfbf9c6d1bf9c105299af13be`.
> The authorization binds the dependency-complete runtime identity reported by
> the offline authorization command. Maximum calls are `1`, retries are `0`,
> the total independent Capstone ceiling is USD `1.00000000`, the V2
> reservation is USD `0.05169700`, cumulative worst-case validation exposure
> is USD `0.10339400`, and remaining validation ceiling is USD `0.89660600`.
> The V1 exposure and strict pending-cost reconciliation remain unchanged.
> Strict-pilot execution, scored execution, winner selection, and production
> deployment are not authorized.

Only after that instruction is present, construct its hash-bound record with a
fresh canonical UTC-seconds timestamp and run the final offline preflight:

```sh
CAPSTONE_AUTHORIZED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)

"$CAPSTONE_PYTHON" -m app.services.evaluation_capstone_live_validation_cli authorization \
  --repository-head "$CAPSTONE_HEAD" \
  --case-id capval-openai-terra-pt1-v2 \
  --authorized-at-utc "$CAPSTONE_AUTHORIZED_AT" \
  --confirm-explicit-user-authorization \
  > /tmp/capval-openai-terra-pt1-v2.authorization.json
chmod 600 /tmp/capval-openai-terra-pt1-v2.authorization.json

"$CAPSTONE_PYTHON" -m app.services.evaluation_capstone_live_validation_cli preflight \
  --repository-head "$CAPSTONE_HEAD" \
  --authorization /tmp/capval-openai-terra-pt1-v2.authorization.json
```

Both commands are offline. The following is the only command in this workflow
that can make a real provider call. Do not run it until the exact V2 human
authorization above exists and `OPENAI_API_KEY` is privately present in the
same shell:

```sh
"$CAPSTONE_PYTHON" -m app.services.evaluation_capstone_live_validation_cli execute \
  --repository-head "$CAPSTONE_HEAD" \
  --case-id capval-openai-terra-pt1-v2 \
  --authorization /tmp/capval-openai-terra-pt1-v2.authorization.json \
  --confirm-live
```

The command validates the same runtime identity before reading the credential,
revalidates the immutable V1 predecessor state, creates a new ignored mode-0600
V2 reservation marker immediately before transport, performs at most one
invocation with redirects disabled and no retry, writes a safe V2 result, and
stops. Either V2 reservation or result marker blocks replay. V1 files are never
used as V2 state.

## Safe inspection and credential revocation

Inspection is offline and does not expose raw provider prose:

```sh
"$CAPSTONE_PYTHON" -m app.services.evaluation_capstone_live_validation_cli inspect \
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
