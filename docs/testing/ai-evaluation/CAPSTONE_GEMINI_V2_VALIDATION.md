# Corrected Gemini/PT1 V2 Capstone validation

Status: `CAPSTONE_GEMINI_V2_VALIDATION_READY_AWAITING_USER`

This V4 extension prepares only the corrected, single-use Gemini/PT1 V2 case:

- Google Gemini 3.7 Flash / PT1 (`capval-gemini-flash-pt1-v2`)

Gemini V1 is consumed and remains immutable with its HTTP-400 result. Terra
V1/V2 and the accepted Sol V1 result remain immutable history. V2 permits one
physical provider call, has zero retries, and cannot authorize strict-pilot,
scored, winner-selection, or deployment state.

The only request correction is the documented Interactions user-input step:
the V1 outer input object used `role: "user"`; V2 uses
`type: "user_input"`. Its content, trusted instruction, fixture, prompts,
canonical schema, model, reasoning level, output cap, storage, and streaming
settings are unchanged.

## Runtime and offline dry run

Use the dependency-complete runtime already established for this worktree:

```sh
cd /Users/ahmed/Projects/trustai-ai-model-evaluation/backend
CAPSTONE_PYTHON=/Users/ahmed/Projects/trustai-marketplace/backend/.venv/bin/python
CAPSTONE_HEAD=$(git -C .. rev-parse HEAD)
```

This dry run is offline. It validates the corrected request, immutable
Terra/Sol/Gemini-V1 history, dependency/runtime identity, transport projection,
authorization shape, and exact exposure without reading a credential:

```sh
env -u OPENAI_API_KEY -u GEMINI_API_KEY -u GROQ_API_KEY \
  PYTHONDONTWRITEBYTECODE=1 \
  "$CAPSTONE_PYTHON" \
  -m app.services.evaluation_capstone_gemini_v2_validation_cli dry-run \
  --repository-head "$CAPSTONE_HEAD" \
  --case-id capval-gemini-flash-pt1-v2
```

## Exact human authorization

Before constructing an authorization record, the user must provide exactly the
following wording with `<CURRENT_COMMITTED_HEAD_SHA>` replaced by the current
committed HEAD:

> I explicitly authorize exactly one `capstone_live_validation` provider invocation at repository HEAD `<CURRENT_COMMITTED_HEAD_SHA>` for validation case `capval-gemini-flash-pt1-v2`, predecessor case `capval-gemini-flash-pt1-v1`, predecessor reservation record hash `a891cb4fb77d86c073ff204fbdaffd0ff5d05d3e05a9c88d778e273a3b6e4c01`, predecessor result record hash `222a10f499873278a526e12bd1c44b62d104a07f477162b1bba75860db488da8`, predecessor HTTP status `400`, and preserved Sol result record hash `352beabadd1ee86c0bc51f7b4c20dcfc66d2fd1574a947f1ef64660e43b4e167`; source call `call-0005`, candidate `gemini_unified_v1`, provider `Google Gemini`, model `gemini-3.7-flash`, fixture `PT1`, workload `text_analysis`, request configuration `gemini_flash_text_pilot_v1` with hash `8644e02a24cff69f6619f744e02c6b55648e9463f76b30453b81dc04edbe466b`, corrected request hash `7ba77e1a55b8171d55d95aff39a7ffb171f8ba4eaf91a3dba342754ec4f57640`, request-builder hash `3d1a3e796d8935f510260eb7673acfea064bf6db17c46f09df7d87605436336d`, transport binding `capstone_gemini_v2_httpx_transport_v1` with implementation hash `58dfb5ed2c3dc7ef51c24c88d53019fb8f4a3e06a528c8cc8d8af1790f66c218`, and Capstone V4 contract hash `8a9632559202da1849f83afc4cd38e5a20d4cb29b2cff7c57f9705c528722a7a`. The authorization binds the dependency-complete runtime identity reported by the offline authorization command and confirms the dedicated `GEMINI_API_KEY` is privately ready, billing is not enabled, the project remains on the Free tier, setup usage is `0`, and the observed Gemini 3.7 Flash limits are `5` requests per minute and `250,000` tokens per minute. Maximum calls are `1`, retries are `0`, the total independent Capstone ceiling is `USD 1.00000000`, preserved historical conservative exposure is `USD 0.21030200`, Gemini V2 Free-tier external monetary exposure is `USD 0.00000000`, cumulative worst-case validation exposure is `USD 0.21030200`, and remaining validation ceiling is `USD 0.78969800`. Free-tier zero is only the Capstone external monetary-exposure treatment; it does not alter strict Gemini pricing. Gemini V1 remains consumed, and existing Terra exposure and strict pending-cost reconciliation remain unchanged. Strict-pilot execution, scored execution, winner selection, and production deployment are not authorized.

Only after that exact authorization exists, construct its record and preflight
offline:

```sh
CAPSTONE_AUTHORIZED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)

env -u OPENAI_API_KEY -u GEMINI_API_KEY -u GROQ_API_KEY \
  PYTHONDONTWRITEBYTECODE=1 \
  "$CAPSTONE_PYTHON" \
  -m app.services.evaluation_capstone_gemini_v2_validation_cli authorization \
  --repository-head "$CAPSTONE_HEAD" \
  --case-id capval-gemini-flash-pt1-v2 \
  --authorized-at-utc "$CAPSTONE_AUTHORIZED_AT" \
  --confirm-explicit-user-authorization \
  > /tmp/capval-gemini-flash-pt1-v2.authorization.json
chmod 600 /tmp/capval-gemini-flash-pt1-v2.authorization.json

env -u OPENAI_API_KEY -u GEMINI_API_KEY -u GROQ_API_KEY \
  PYTHONDONTWRITEBYTECODE=1 \
  "$CAPSTONE_PYTHON" \
  -m app.services.evaluation_capstone_gemini_v2_validation_cli preflight \
  --repository-head "$CAPSTONE_HEAD" \
  --case-id capval-gemini-flash-pt1-v2 \
  --authorization /tmp/capval-gemini-flash-pt1-v2.authorization.json
```

## Real Gemini call — do not run without separate authorization

This is the only command that can make the V2 provider call. It must be run
only from the same private shell containing `GEMINI_API_KEY`, after the exact
authorization and both offline commands pass:

```sh
"$CAPSTONE_PYTHON" \
  -m app.services.evaluation_capstone_gemini_v2_validation_cli execute \
  --repository-head "$CAPSTONE_HEAD" \
  --case-id capval-gemini-flash-pt1-v2 \
  --authorization /tmp/capval-gemini-flash-pt1-v2.authorization.json \
  --confirm-live
```

## Safe offline inspection

```sh
env -u OPENAI_API_KEY -u GEMINI_API_KEY -u GROQ_API_KEY \
  PYTHONDONTWRITEBYTECODE=1 \
  "$CAPSTONE_PYTHON" \
  -m app.services.evaluation_capstone_gemini_v2_validation_cli inspect \
  --repository-head "$CAPSTONE_HEAD" \
  --case-id capval-gemini-flash-pt1-v2
```

Credentials must never be placed in Git, fixtures, authorizations, result
records, logs, command arguments, or chat. Remove the runtime variable from the
private shell when the observation is complete.
