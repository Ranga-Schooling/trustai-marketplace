# Terra production text smoke

This is a prepared, synthetic, pre-deployment check of the D-21 production
OpenAI Responses adapter. It is inert until a human separately authorizes the
exact committed HEAD and descriptor. It is not an evaluation run, scored run,
deployment, database write, or Visual Inspection request.

## Versioned smoke boundary

`terra-production-text-smoke-v1` was prepared against an earlier repository
HEAD but was never executed. Its identity must not be reused after adding the
safe evidence contract. The current identity is:

- Smoke ID: `terra-production-text-smoke-v2`
- Result contract: `terra-production-text-smoke-result-v2`
- Fixture ID: `terra-production-text-smoke-synthetic-v1`
- Provider/model: OpenAI / `gpt-5.6-terra`
- Endpoint: `POST https://api.openai.com/v1/responses`
- Request configuration: `terra-production-responses-text-v1`
- Maximum physical attempts: 1
- Retries: 0
- Timeout: 30 seconds
- Maximum output: 2,048 tokens
- Storage/streaming/tools: disabled
- Database writes: none
- Raw provider response retention: none

The descriptor is built by the exact production request builder. It binds the
committed HEAD, prompt version/hash, generated schema hash, configuration hash,
synthetic fixture hash, canonical request hash, request byte count, and a
conservative cost ceiling. The input-token upper bound is the canonical
request's UTF-8 byte length (one token per byte), charged at the Terra
short-context uncached-input rate, plus the full 2,048-token output allowance.
A current provider pricing check remains required before human authorization.

## Safe evidence contract

The live path writes one canonical, hash-bound `result.json`. It retains only
the smoke and repository identities, safe endpoint label, terminal status,
attempt/retry count, numeric HTTP status, monotonic latency, documented numeric
usage, an exact-Decimal cost estimate, the certified ceiling, independent
parser/schema/validator/evidence-policy/mapping outcomes, and SHA-256 identities
of the raw response bytes and normalized `AIAnalysisResult`. It never retains
or prints provider prose, raw response bytes, the authorization header, or the
API key. The estimate is not provider billing.

The smoke charges uncached input at USD 2.00/M, cached input at USD 0.20/M,
and output at USD 12.00/M. Reasoning tokens are a subset of output tokens and
are not charged twice. Missing or malformed usage, a cost above the certified
ceiling, or any failed validation stage makes the result ineligible to pass.

The packet directory is mode `0700`; authorization, attempt marker, and result
files are mode `0600`. The attempt marker is created atomically before provider
construction. The result is published atomically without overwrite. Once a
physical request is attempted, the smoke identity is consumed whether it
succeeds or fails.

## Offline preparation

Run from a clean `integration/capstone-final` checkout after substituting the
committed HEAD. Build the application-only image from that exact checkout:

```bash
docker build --tag trustai-capstone-final-api:terra-smoke-v2 backend
```

Describe the exact identity without forwarding `OPENAI_API_KEY`:

```bash
test "$(git rev-parse HEAD)" = "<COMMITTED_HEAD>" && \
test -z "$(git status --porcelain)" && \
docker run --rm --network none \
  --user "$(id -u):$(id -g)" \
  trustai-capstone-final-api:terra-smoke-v2 \
  python -m scripts.terra_text_smoke describe \
  --repository-head <COMMITTED_HEAD>
```

Initialize the private, unauthorized packet exactly once:

```bash
test ! -e /private/tmp/trustai-terra-production-text-smoke-v2 && \
docker run --rm --network none \
  --user "$(id -u):$(id -g)" \
  -v /private/tmp:/packets \
  trustai-capstone-final-api:terra-smoke-v2 \
  python -m scripts.terra_text_smoke initialize \
  --repository-head <COMMITTED_HEAD> \
  --packet-dir /packets/trustai-terra-production-text-smoke-v2
```

Only after the human gives exact authorization, create the closed authorization
record from the descriptor. These commands do not receive a credential:

```bash
umask 077
docker run --rm --network none \
  --user "$(id -u):$(id -g)" \
  trustai-capstone-final-api:terra-smoke-v2 \
  python -m scripts.terra_text_smoke describe \
  --repository-head <COMMITTED_HEAD> \
  > /private/tmp/trustai-terra-production-text-smoke-v2/descriptor.json
python3 -c 'import json,sys; p=json.load(open(sys.argv[1], encoding="utf-8")); p.update(authorization_scope="production_text_smoke", authorized=True); open(sys.argv[2], "x", encoding="utf-8").write(json.dumps(p, allow_nan=False, sort_keys=True, separators=(",", ":")))' \
  /private/tmp/trustai-terra-production-text-smoke-v2/descriptor.json \
  /private/tmp/trustai-terra-production-text-smoke-v2/authorization.json
chmod 600 \
  /private/tmp/trustai-terra-production-text-smoke-v2/descriptor.json \
  /private/tmp/trustai-terra-production-text-smoke-v2/authorization.json
```

Validate the authorization and unused packet offline:

```bash
test "$(git rev-parse HEAD)" = "<COMMITTED_HEAD>" && \
test -z "$(git status --porcelain)" && \
docker run --rm --network none \
  --user "$(id -u):$(id -g)" \
  -v /private/tmp/trustai-terra-production-text-smoke-v2:/packet:ro \
  trustai-capstone-final-api:terra-smoke-v2 \
  python -m scripts.terra_text_smoke preflight \
  --repository-head <COMMITTED_HEAD> \
  --authorization-file /packet/authorization.json \
  --packet-dir /packet
```

## Live boundary — do not run without exact authorization

The future command verifies the same clean HEAD, requires credential presence,
forwards the credential only at the container boundary, validates the closed
authorization and production request identity, forces the real production
adapter to one attempt, and publishes only safe evidence.

```bash
test "$(git rev-parse HEAD)" = "<COMMITTED_HEAD>" && \
test -z "$(git status --porcelain)" && \
test -n "${OPENAI_API_KEY:-}" && \
docker run --rm --network bridge \
  --user "$(id -u):$(id -g)" \
  -e OPENAI_API_KEY \
  -e OPENAI_MODEL=gpt-5.6-terra \
  -v /private/tmp/trustai-terra-production-text-smoke-v2:/packet \
  trustai-capstone-final-api:terra-smoke-v2 \
  python -m scripts.terra_text_smoke execute \
  --repository-head <COMMITTED_HEAD> \
  --authorization-file /packet/authorization.json \
  --packet-dir /packet
```

Never rerun that command after a physical provider request, including after a
failure. A later attempt requires a new versioned smoke identity and a new
human authorization.

## Safe offline inspection

Inspection needs neither a credential nor network access. It verifies packet
permissions, the exact smoke/repository identity, the closed field inventory,
the canonical record hash, usage/cost invariants, stage ordering, and PASS
conditions before printing the safe result projection:

```bash
test "$(git rev-parse HEAD)" = "<COMMITTED_HEAD>" && \
test -z "$(git status --porcelain)" && \
docker run --rm --network none \
  --user "$(id -u):$(id -g)" \
  -v /private/tmp/trustai-terra-production-text-smoke-v2:/packet:ro \
  trustai-capstone-final-api:terra-smoke-v2 \
  python -m scripts.terra_text_smoke inspect \
  --repository-head <COMMITTED_HEAD> \
  --packet-dir /packet
```

PASS requires one physical request maximum, zero retries, HTTP 200, usage
present, cost at or below the certified ceiling, every validation/mapping stage
passed, valid raw-response and normalized-semantic hashes, private immutable
evidence, and an unchanged repository. Strict pilot/scored execution, model
selection, deployment, and any additional provider call remain outside this
smoke authorization.
