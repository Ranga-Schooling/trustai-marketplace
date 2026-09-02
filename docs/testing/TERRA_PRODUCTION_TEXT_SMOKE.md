# Terra production text smoke

This is a prepared, synthetic, pre-deployment check of the D-21 production
OpenAI Responses adapter. It is inert until a human separately authorizes the
exact committed HEAD and descriptor. It is not an evaluation run, scored run,
deployment, database write, or Visual Inspection request.

## Frozen smoke boundary

- Smoke ID: `terra-production-text-smoke-v1`
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
request's UTF-8 byte length (one token per byte), charged at the frozen Terra
short-context uncached-input rate, plus the full 2,048-token output allowance
at the frozen output rate. A current provider pricing check is still required
before human authorization.

## Offline preparation

Run from a clean `integration/capstone-final` checkout after substituting the
committed HEAD. Do not forward `OPENAI_API_KEY` to either offline command.
Build the application-only smoke image from that exact clean checkout first:

```bash
docker build --tag trustai-capstone-final-api:smoke backend
```

```bash
test "$(git rev-parse HEAD)" = "<COMMITTED_HEAD>" && \
test -z "$(git status --porcelain)" && \
docker run --rm --network none \
  trustai-capstone-final-api:smoke \
  python -m scripts.terra_text_smoke describe \
  --repository-head <COMMITTED_HEAD>
```

After the human supplies an authorization file containing exactly the printed
descriptor plus `"authorization_scope":"production_text_smoke"` and
`"authorized":true`, validate it offline:

```bash
test "$(git rev-parse HEAD)" = "<COMMITTED_HEAD>" && \
test -z "$(git status --porcelain)" && \
docker run --rm --network none \
  -v /private/tmp/trustai-terra-production-text-smoke-v1:/packet:ro \
  trustai-capstone-final-api:smoke \
  python -m scripts.terra_text_smoke preflight \
  --repository-head <COMMITTED_HEAD> \
  --authorization-file /packet/authorization.json \
  --packet-dir /packet
```

## Live boundary — do not run without exact authorization

The future live command must first verify the same clean HEAD, then explicitly
forward the private shell's credential into the container. The script validates
the closed authorization and production request identity before constructing
the provider, forces the actual production adapter to one attempt, and emits
only hashes plus safe status fields.

```bash
test "$(git rev-parse HEAD)" = "<COMMITTED_HEAD>" && \
test -z "$(git status --porcelain)" && \
docker run --rm --network bridge \
  -e OPENAI_API_KEY \
  -e OPENAI_MODEL=gpt-5.6-terra \
  -v /private/tmp/trustai-terra-production-text-smoke-v1:/packet \
  trustai-capstone-final-api:smoke \
  python -m scripts.terra_text_smoke execute \
  --repository-head <COMMITTED_HEAD> \
  --authorization-file /packet/authorization.json \
  --packet-dir /packet
```

The live mode atomically creates `/packet/attempt-started.json` before
constructing the provider. The marker remains after success or failure, so the
same packet cannot be used for a second physical attempt. This command is
documentation only. No credential was accessed and no provider call was made
while preparing it.
