# Capstone cross-provider text validation

Status: `CAPSTONE_CROSS_PROVIDER_TEXT_VALIDATION_READY_AWAITING_USER`

This V3 extension prepares only the remaining minimum real text observations:

- OpenAI Sol / PT1 (`capval-openai-sol-pt1-v1`)
- Google Gemini 3.7 Flash / PT1 (`capval-gemini-flash-pt1-v1`)

The accepted Terra/PT1 V2 result remains immutable history. Each new case is
single-use, requires a separate exact human authorization, permits one physical
provider call, has zero retries, and stops before any next case. Neither result
is a strict-pilot record, scored record, winner-selection input, or production
deployment authority.

## Runtime and offline status

Use the dependency-complete runtime already established for this worktree:

```sh
cd /Users/ahmed/Projects/trustai-ai-model-evaluation/backend
CAPSTONE_PYTHON=/Users/ahmed/Projects/trustai-marketplace/backend/.venv/bin/python
CAPSTONE_HEAD=$(git rev-parse HEAD)

env -u OPENAI_API_KEY -u GEMINI_API_KEY -u GROQ_API_KEY \
  PYTHONDONTWRITEBYTECODE=1 \
  "$CAPSTONE_PYTHON" \
  -m app.services.evaluation_capstone_cross_provider_validation_cli status
```

The following dry runs are offline. They validate immutable Terra history,
frozen requests, the dependency/runtime identity, transport projection,
authorization shape, and exact conservative exposure without reading a
credential or calling a provider:

```sh
env -u OPENAI_API_KEY -u GEMINI_API_KEY -u GROQ_API_KEY \
  PYTHONDONTWRITEBYTECODE=1 \
  "$CAPSTONE_PYTHON" \
  -m app.services.evaluation_capstone_cross_provider_validation_cli dry-run \
  --repository-head "$CAPSTONE_HEAD" \
  --case-id capval-openai-sol-pt1-v1

env -u OPENAI_API_KEY -u GEMINI_API_KEY -u GROQ_API_KEY \
  PYTHONDONTWRITEBYTECODE=1 \
  "$CAPSTONE_PYTHON" \
  -m app.services.evaluation_capstone_cross_provider_validation_cli dry-run \
  --repository-head "$CAPSTONE_HEAD" \
  --case-id capval-gemini-flash-pt1-v1
```

## Sol/PT1 authorization

Before constructing a Sol authorization record, the user must provide exactly
the following wording with `<CURRENT_COMMITTED_HEAD_SHA>` replaced by the
current committed HEAD:

> I explicitly authorize exactly one `capstone_live_validation` provider invocation at repository HEAD `<CURRENT_COMMITTED_HEAD_SHA>` for validation case `capval-openai-sol-pt1-v1`, historical predecessor case `capval-openai-terra-pt1-v2`, Terra V1 reservation record hash `a9d604c30f16ecd4525d533955f9701ea15ed78c35cb7fff703c3e3761cd1bab`, Terra V1 result record hash `554fdf1685a4b766698d9af255fd7921e3500a7390915957831eab440582d24e`, Terra V2 reservation record hash `6a66fa758fa20d231a02649263fddcdb53da314b2a1f6a9c9853b10e58610ed3`, and Terra V2 result record hash `1c4b25beb71569d68642e9f6d554b7473d042c779b8f26c930ca63caa9959386`; source call `call-0001`, candidate `openai_unified_premium_v1`, provider `OpenAI`, model `gpt-5.6-sol`, fixture `PT1`, workload `text_analysis`, request configuration `openai_sol_text_pilot_v1` with hash `1211deef134ed1fd723a8f0e63b054cae5c4f257138776b02b5b6f6266162caf`, request hash `9ddf9c22ab28c69987944c1a77043cb7ed64aed0f81c283444be4129ad47c47f`, transport binding `capstone_cross_provider_httpx_transport_v1` with implementation hash `58dfb5ed2c3dc7ef51c24c88d53019fb8f4a3e06a528c8cc8d8af1790f66c218`, and Capstone V3 contract hash `fa141065f8fe374d4b43409cefb2fec58e66f3f949d733ea4bf9cdc254635617`. The authorization binds the dependency-complete runtime identity reported by the offline authorization command. The input-token value is not claimed exact; the reservation binds the 6,247-token UTF-8 request-body byte upper bound and 4,096-token output maximum. Maximum calls are `1`, retries are `0`, the total independent Capstone ceiling is `USD 1.00000000`, historical conservative exposure is `USD 0.10339400`, the Sol reservation is `USD 0.10690800`, cumulative worst-case validation exposure is `USD 0.21030200`, and remaining validation ceiling is `USD 0.78969800`. Existing Terra exposure and strict pending-cost reconciliation remain unchanged. Strict-pilot execution, scored execution, winner selection, and production deployment are not authorized.

Only after that exact authorization exists, construct its record and preflight
offline:

```sh
CAPSTONE_AUTHORIZED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)

env -u OPENAI_API_KEY -u GEMINI_API_KEY -u GROQ_API_KEY \
  PYTHONDONTWRITEBYTECODE=1 \
  "$CAPSTONE_PYTHON" \
  -m app.services.evaluation_capstone_cross_provider_validation_cli authorization \
  --repository-head "$CAPSTONE_HEAD" \
  --case-id capval-openai-sol-pt1-v1 \
  --authorized-at-utc "$CAPSTONE_AUTHORIZED_AT" \
  --confirm-explicit-user-authorization \
  > /tmp/capval-openai-sol-pt1-v1.authorization.json
chmod 600 /tmp/capval-openai-sol-pt1-v1.authorization.json

env -u OPENAI_API_KEY -u GEMINI_API_KEY -u GROQ_API_KEY \
  PYTHONDONTWRITEBYTECODE=1 \
  "$CAPSTONE_PYTHON" \
  -m app.services.evaluation_capstone_cross_provider_validation_cli preflight \
  --repository-head "$CAPSTONE_HEAD" \
  --case-id capval-openai-sol-pt1-v1 \
  --authorization /tmp/capval-openai-sol-pt1-v1.authorization.json
```

This is the only Sol command that can make a provider call. Do not run it
without the exact separate Sol authorization and private `OPENAI_API_KEY` in
the same shell:

```sh
"$CAPSTONE_PYTHON" \
  -m app.services.evaluation_capstone_cross_provider_validation_cli execute \
  --repository-head "$CAPSTONE_HEAD" \
  --case-id capval-openai-sol-pt1-v1 \
  --authorization /tmp/capval-openai-sol-pt1-v1.authorization.json \
  --confirm-live
```

## Gemini/PT1 authorization

Before constructing a Gemini authorization record, the user must separately
provide exactly the following wording with `<CURRENT_COMMITTED_HEAD_SHA>`
replaced by the current committed HEAD:

> I explicitly authorize exactly one `capstone_live_validation` provider invocation at repository HEAD `<CURRENT_COMMITTED_HEAD_SHA>` for validation case `capval-gemini-flash-pt1-v1`, historical predecessor case `capval-openai-terra-pt1-v2`, Terra V1 reservation record hash `a9d604c30f16ecd4525d533955f9701ea15ed78c35cb7fff703c3e3761cd1bab`, Terra V1 result record hash `554fdf1685a4b766698d9af255fd7921e3500a7390915957831eab440582d24e`, Terra V2 reservation record hash `6a66fa758fa20d231a02649263fddcdb53da314b2a1f6a9c9853b10e58610ed3`, and Terra V2 result record hash `1c4b25beb71569d68642e9f6d554b7473d042c779b8f26c930ca63caa9959386`; source call `call-0005`, candidate `gemini_unified_v1`, provider `Google Gemini`, model `gemini-3.7-flash`, fixture `PT1`, workload `text_analysis`, request configuration `gemini_flash_text_pilot_v1` with hash `8644e02a24cff69f6619f744e02c6b55648e9463f76b30453b81dc04edbe466b`, request hash `00f29bb98c9840ffb6d1e61fc080c607aa54a2b20ca862c58f862d08ed013584`, transport binding `capstone_cross_provider_httpx_transport_v1` with implementation hash `58dfb5ed2c3dc7ef51c24c88d53019fb8f4a3e06a528c8cc8d8af1790f66c218`, and Capstone V3 contract hash `fa141065f8fe374d4b43409cefb2fec58e66f3f949d733ea4bf9cdc254635617`. The authorization binds the dependency-complete runtime identity reported by the offline authorization command and confirms the dedicated `GEMINI_API_KEY` is privately ready, billing is not enabled, the project remains on the Free tier, setup usage is `0`, and the observed Gemini 3.7 Flash limits are `5` requests per minute and `250,000` tokens per minute. Maximum calls are `1`, retries are `0`, the total independent Capstone ceiling is `USD 1.00000000`, historical conservative exposure plus the reserved Sol allocation is `USD 0.21030200`, Gemini Free-tier external monetary exposure is `USD 0.00000000`, cumulative worst-case validation exposure is `USD 0.21030200`, and remaining validation ceiling is `USD 0.78969800`. Free-tier zero is only the Capstone external monetary-exposure treatment; it does not alter strict Gemini pricing. Existing Terra exposure and strict pending-cost reconciliation remain unchanged. Strict-pilot execution, scored execution, winner selection, and production deployment are not authorized.

Only after that separate exact authorization exists, construct its record and
preflight offline:

```sh
CAPSTONE_AUTHORIZED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)

env -u OPENAI_API_KEY -u GEMINI_API_KEY -u GROQ_API_KEY \
  PYTHONDONTWRITEBYTECODE=1 \
  "$CAPSTONE_PYTHON" \
  -m app.services.evaluation_capstone_cross_provider_validation_cli authorization \
  --repository-head "$CAPSTONE_HEAD" \
  --case-id capval-gemini-flash-pt1-v1 \
  --authorized-at-utc "$CAPSTONE_AUTHORIZED_AT" \
  --confirm-explicit-user-authorization \
  > /tmp/capval-gemini-flash-pt1-v1.authorization.json
chmod 600 /tmp/capval-gemini-flash-pt1-v1.authorization.json

env -u OPENAI_API_KEY -u GEMINI_API_KEY -u GROQ_API_KEY \
  PYTHONDONTWRITEBYTECODE=1 \
  "$CAPSTONE_PYTHON" \
  -m app.services.evaluation_capstone_cross_provider_validation_cli preflight \
  --repository-head "$CAPSTONE_HEAD" \
  --case-id capval-gemini-flash-pt1-v1 \
  --authorization /tmp/capval-gemini-flash-pt1-v1.authorization.json
```

This is the only Gemini command that can make a provider call. Do not run it
without the exact separate Gemini authorization and private `GEMINI_API_KEY`
in the same shell:

```sh
"$CAPSTONE_PYTHON" \
  -m app.services.evaluation_capstone_cross_provider_validation_cli execute \
  --repository-head "$CAPSTONE_HEAD" \
  --case-id capval-gemini-flash-pt1-v1 \
  --authorization /tmp/capval-gemini-flash-pt1-v1.authorization.json \
  --confirm-live
```

## Safe inspection

Inspection is offline and exposes only the safe result projection:

```sh
"$CAPSTONE_PYTHON" \
  -m app.services.evaluation_capstone_cross_provider_validation_cli inspect \
  --repository-head "$CAPSTONE_HEAD" \
  --case-id <AUTHORIZED_CASE_ID>
```

Credentials must never be placed in Git, fixtures, authorizations, result
records, logs, command arguments, or chat. Remove the runtime variable from the
private shell when the observation is complete.
