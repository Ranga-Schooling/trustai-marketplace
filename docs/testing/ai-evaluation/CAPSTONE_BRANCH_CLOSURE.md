# Capstone AI-evaluation branch closure

Status: `CAPSTONE_LIVE_PROVIDER_VALIDATION_COMPLETE`

This document closes the Capstone-critical evaluation work on
`research/ai-model-evaluation`. It records the minimum privacy-safe evidence
needed to review the branch without promoting a model, weakening the strict
research evaluator, or committing ignored operational state.

The live-validation source snapshot is
`dbc19ef41f115c00e86e0877e3e07add5e747e7a`. The branch started from
`9cdf5cc1870ed0f4cb891b63be60ae1c3d57fbe5` (`origin/main` as locally
recorded during closure). The 60 commits between those snapshots are
intentional chronological research history, not a single simultaneously
designed production feature.

## Scope and non-claims

The bounded Capstone objective is complete for:

1. OpenAI Terra with PT1;
2. OpenAI Sol with PT1;
3. Google Gemini 3.7 Flash with PT1.

The observations establish current text-request, structured-output, parser,
schema, and deterministic-validator interoperability for the three successful
cases below. They do **not** establish comparative quality, rank a model,
select a winner, change TrustAI's production model, authorize scored
execution, or authorize deployment.

PT2, visual, search/retrieval, synthesis, Groq, the complete strict pilot,
randomized/blinded execution, grading anchors, calibration, adjudication,
scoring, dashboards, and long-term automation are explicitly deferred beyond
the Capstone critical path.

## Research chronology

The branch evolved through distinct reviewed phases:

- `992913a` through `e2a88ef`: methodology, experiment, pilot fixtures,
  prompts, schemas, parser, and ownership contracts were frozen.
- `d3a2ba3` through `a9a986e`: URL security, normalization, bounded resources,
  privacy, result records, retry, search authority, role mappings, adapters,
  request configurations, region, pricing, and budget controls were built and
  tested provider-free.
- `ccf26a2` through `9ae9a51`: the provider-free runner, fail-closed live
  boundary, and single-use OpenAI input-token preflight were added.
- `b5f1916` through `440880a`: bounded Terra V1/V2 validation exposed and
  corrected runtime dependency, response-lifecycle, and replay-preflight
  defects.
- `6f271fa`: cross-provider Sol/Gemini text validation was prepared.
- `dbc19ef`: Gemini's Interactions `user_input` envelope was corrected after
  the consumed V1 HTTP-400 observation.

Historical contracts and consumed cases remain versioned and immutable.

## Authoritative external-operation history

### OpenAI input-token preflight

- Target: `call-0003`, Terra/PT1.
- Endpoint: `POST /v1/responses/input_tokens`.
- Invocation count: 1; retries: 0; model response generated: false.
- Observed at: `2026-09-01T20:23:44Z`.
- Input tokens: 1,018.
- Original request hash:
  `97f8752bb33994a00018a15ff62d79419069397b223cc5f60770def973ebc266`.
- Token-count request hash:
  `845696e3a79e59c1285d8da68f6ec707222cec6196ba8bab1a092aaec1a35e41`.
- Raw-response hash:
  `94aa84b722e2068ab1a1d6c9b5ce4d7a22afe4b5c6a84b91e0254ff80d548a35`.
- Evidence semantic hash:
  `e9d891dee0d400897f57cc083e270b8dc8eea91d1fdcc5b792f4828278fc43ea`.
- Derived Terra reservation: USD `0.05169700`.
- Accounting state: `pending_cost_reconciliation`.

The original complete token-count evidence document is not stored in this
worktree. Its supplied semantic hash therefore cannot be independently
recomputed from branch bytes during closure. The recorded identities and
1,018-token result are corroborated by the accepted Terra V2 provider usage,
but that corroboration does not reconcile or replace the missing accounting
evidence.

### Terra/PT1 V1 — stopped

- Case: `capval-openai-terra-pt1-v1`.
- Reservation:
  `a9d604c30f16ecd4525d533955f9701ea15ed78c35cb7fff703c3e3761cd1bab`.
- Result:
  `554fdf1685a4b766698d9af255fd7921e3500a7390915957831eab440582d24e`.
- Outcome: stopped with safe failure `connection`.
- Attempts: 1; retries: 0.
- Parser/schema/validator: not reached.

Later offline investigation found a missing dependency-complete-runtime
preflight and premature `httpx.Response.elapsed` access before streamed
response closure. Both were corrected and regression-tested, together with a
replay-preflight defect. The V1 record does not contain enough diagnostic
detail to claim which physical sublayer caused its observed failure.

### Terra/PT1 V2 — accepted

- Case: `capval-openai-terra-pt1-v2`.
- Reservation:
  `6a66fa758fa20d231a02649263fddcdb53da314b2a1f6a9c9853b10e58610ed3`.
- Result:
  `1c4b25beb71569d68642e9f6d554b7473d042c779b8f26c930ca63caa9959386`.
- Attempts: 1; retries: 0; latency: `6.897342833050061` seconds.
- Usage: 1,018 input, 181 output, 0 reasoning tokens.
- Parser/schema/validator: passed/passed/passed.
- Estimated cost: USD `0.004208`, derived from provider usage and the frozen
  pricing snapshot; not authoritative provider billing.
- Raw-response hash:
  `be572ab8068291a1f87eb8ab044f49455722c3b292d02f09c80a3b50419493dd`.
- Normalized semantic hash:
  `acd669b9dd5a39940c4869e87ef7224289d0ea8f1f1fdf80059467c358b98e4a`.

### Sol/PT1 — accepted

- Case: `capval-openai-sol-pt1-v1`.
- Reservation:
  `115405478d45a6cedfb406bf774dfd9a7f47df186f01513f557797c1e815be2a`.
- Result:
  `352beabadd1ee86c0bc51f7b4c20dcfc66d2fd1574a947f1ef64660e43b4e167`.
- Attempts: 1; retries: 0; latency: `4.029280124988873` seconds.
- Usage: 1,018 input, 151 output, 0 reasoning tokens.
- Parser/schema/validator: passed/passed/passed.
- Estimated cost: USD `0.007092`, derived from provider usage and the frozen
  pricing snapshot; not authoritative provider billing.
- Raw-response hash:
  `13e1367c59237d999f216ec461670908e3b08b5f096ad9dd961f59a4f36548bf`.
- Normalized semantic hash:
  `8f3e1960a0fb8e49170cba210197bd0a16a61782932bd7f9644a2ca57955627d`.

### Gemini/PT1 V1 — stopped

- Case: `capval-gemini-flash-pt1-v1`.
- Reservation:
  `a891cb4fb77d86c073ff204fbdaffd0ff5d05d3e05a9c88d778e273a3b6e4c01`.
- Result:
  `222a10f499873278a526e12bd1c44b62d104a07f477162b1bba75860db488da8`.
- HTTP status: 400; safe failure: `http_failure`.
- Attempts: 1; retries: 0; latency: `0.28190220904070884` seconds.
- Parser/schema/validator: not reached.
- Raw-response hash:
  `9cfc3b4a362e7f72f74843cf60e0c842aadcd07546c919afb12c1189a327fc5c`.

The strongly supported cause was a deterministic Interactions request-envelope
defect: V1 used `{"role":"user","content":[...]}` where the current API
requires `{"type":"user_input","content":[...]}`. The provider's error
body/type was intentionally not retained, so the record does not independently
confirm that diagnosis.

### Gemini/PT1 V2 — accepted

- Case: `capval-gemini-flash-pt1-v2`.
- Corrected request hash:
  `7ba77e1a55b8171d55d95aff39a7ffb171f8ba4eaf91a3dba342754ec4f57640`.
- Reservation:
  `407bc06a4c4910a1af525b22d7ebcd7ba2448d45be33d81b9d640320702aaa99`.
- Result:
  `6657b09a95c4e426b33cacdf638665d1e9f150f70895dd7bb8c6631c6a415151`.
- Attempts: 1; retries: 0; latency: `23.077975874999538` seconds.
- Usage: 867 input, 170 output, 476 reasoning tokens.
- Parser/schema/validator: passed/passed/passed.
- Billing context: Free tier, billing disabled.
- Capstone external monetary exposure: USD `0.00000000`. This is only the
  bounded Free-tier exposure treatment and does not alter strict Gemini
  pricing.
- Raw-response hash:
  `5058d1efeb85a7b8e44ad530c007da4d740c6a03dfbb4b3652ad4bacbcab838e`.
- Normalized semantic hash:
  `c361668782bd756e05e9ccef4402d91fc3dcc3fbeb7ed8ed3ed2291e97e25a03`.

All three accepted results use `text_output_schema_v1` and contain exactly:
`price_assessment`, `price_plausibility`, `recommendation`,
`risk_indicators`, `risk_level`, `seller_questions`, and `summary`.

## Record, privacy, and exposure audit

The five reservation/result pairs remain outside Git under the ignored
`.capstone-live-validation/` directory. At closure:

- all 10 `record_hash` values independently recomputed from canonical records;
- reservation/result authorization, request, contract, repository, and case
  bindings matched;
- predecessor links and historical Terra/Sol/Gemini hashes matched V2/V3/V4;
- every result recorded exactly one physical attempt and zero retries;
- replay protection remained active because every consumed case retained its
  exclusive reservation and result;
- every operational file was mode `0600`;
- ordinary records contained no credential material, raw provider prose, raw
  restricted trace, raw search query, or raw tool arguments;
- strict-pilot, scored-record, winner-selection, and production-deployment
  flags were false for every result.

The independent Capstone ceiling remains USD `1.00000000`. Preserved
worst-case exposure is USD `0.21030200`, leaving USD `0.78969800`. This
Capstone accounting does not modify the strict pilot ledger.

The strict evaluator remains fail-closed at `pending_cost_reconciliation`.
The empty OpenAI Cost Data bucket is not interpreted as exact zero; no waiver,
reconciliation, deletion, or bypass is recorded here.

High-confidence secret scanning found no real credential in current tracked
content, branch history, or operational records. One history match is an
intentional synthetic bearer-token test vector. The operator guides retain two
machine-specific runtime paths as historical command provenance; they contain
no credential value. No billing export, screenshot, private key, `.env`, or
live authorization file is tracked.

## Frozen identities and execution boundary

Provider-neutral preflight successfully binds the frozen methodology,
experiment, fixtures, rubric, prompt set, output-schema set, parser and its
registered policies, Search Authority V2, source/trace policies, role mappings,
adapters, request configurations, retry/resource/privacy/result-record rules,
region, pricing, and budget controls.

Capstone contract semantic hashes independently recompute as:

- V1: `389c8e4c693fc9bcff353f9704c104f8ec64ba98de05c3a6d9c0cd7e6eec7564`;
- V2: `48831c6dfafcdd00ab7e8a525d448574526ffefbfbf9c6d1bf9c105299af13be`;
- V3: `fa141065f8fe374d4b43409cefb2fec58e66f3f949d733ea4bf9cdc254635617`;
- V4: `8a9632559202da1849f83afc4cd38e5a20d4cb29b2cff7c57f9705c528722a7a`.

The committed experiment and strict runner still report provider calls,
pilot calls, scored calls, and winner selection as disallowed or pending. The
accepted Capstone observations are separate validation evidence and cannot be
promoted into strict or scored results.

## TrustAI Marketplace integration strategy

This branch adds isolated evaluation contracts, services, tests, synthetic
pilot assets, operator documentation, and a Git ignore rule. It does not wire
the evaluator into application routes, change production provider/model
configuration, select a model, or deploy anything.

Integration should preserve the reviewed research chronology:

1. refresh remote references read-only and normally merge current
   `origin/main` into this branch only if it has moved;
2. rerun required CI after any synchronization;
3. push this branch normally without force;
4. open one non-draft PR from `research/ai-model-evaluation` to `main`;
5. review the frozen-contract and security boundaries plus the final CI state;
6. merge using a normal merge commit rather than squash/rebase so the
   governance and corrective sequence remains inspectable.

No push, PR, merge, release, or deployment is part of this closure commit.

## Final offline validation

The final closure audit produced:

- focused Capstone/live-boundary suite: 113 passed, 0 failed;
- provider-neutral evaluation suite: 2,538 passed, 0 failed;
- complete backend suite: 2,735 passed, 0 failed;
- total backend coverage: 88.97%; required gate: 85%;
- strict JSON: 33 committed contract files and 10 local operational records
  passed UTF-8, duplicate-key, non-finite, and Unicode-scalar validation;
- all 10 operational record hashes and all four Capstone contract semantic
  hashes independently recomputed;
- AST/compilation, privacy/secret, and whitespace checks: passed;
- P0/P1/P2 findings: none.

The complete suite emitted 81 existing framework/test warnings covering
Starlette/FastAPI/Pydantic deprecations, short synthetic JWT test keys, and the
known Starlette 422-name deprecation. No warning represented a failure of the
evaluation contracts or live-validation boundary.

## Final state

For the Capstone critical path:

- live-provider integration validation: **complete**;
- strict research evaluator: **preserved and fail-closed**;
- strict pilot: **not executed**;
- scored evaluation: **not executed**;
- winner selected: **no**;
- production model changed: **no**;
- deployment performed: **no**;
- further evaluation expansion on this branch: **stopped**.
