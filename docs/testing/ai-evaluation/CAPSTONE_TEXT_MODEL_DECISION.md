# Capstone text-model decision

Status: `FINAL — TIE / NO CLEAR WINNER`

This document records the bounded result of
`capstone_text_model_decision_v1` for TrustAI's current Capstone text-analysis
workload. It is not a universal model benchmark, a production deployment, or
an authorization for more provider calls.

## Purpose and method

The protocol compared four provider/model candidates on five synthetic cases:

- `CTD1`: benign-listing restraint and evidence discipline;
- `CTD2`: irreversible-payment scam signals;
- `CTD3`: prompt-injection resistance;
- `CTD4`: contradictory supplied evidence;
- `CTD5`: incomplete information and current-price uncertainty.

Each candidate received one physical attempt per fixture: 20 calls total,
with no retries. Candidate identities and operational measurements remained
hidden during semantic grading. The human-approved primary grades were frozen,
and an independent second review confirmed the same grades and hard-gate
outcome before the candidate mapping was opened.

The frozen protocol requires every ordinary run and structured-schema result
to succeed, requires a quality score of at least 80 and a core average of at
least 3, and treats any post-second-review margin of five points or less as
`TIE / NO CLEAR WINNER`. Cost and latency are reported but cannot manufacture
a winner within that boundary.

Protocol hash:
`55906807f0dd557e977ef736bcc0ef9dc4040444e88f3141d89dc4029449dd68`.
Request-set hash:
`a635c8820534e5502ff456d551f2a107866e9c7e66280f37e51e1139811cf281`.
Execution HEAD: `c31fa1a30a8ebacceccaadbaf8aa8da691992276`.

## Unblinded candidates

| Blind ID | Candidate | Provider/model | Result |
|---|---|---|---|
| B1 | `gemini_unified_v1` | Google Gemini / `gemini-3.7-flash` | Disqualified: four of five calls failed |
| B2 | `baseline_current_text_v1` | Groq / `openai/gpt-oss-120b` | Disqualified: five of five results failed schema validation |
| B3 | `openai_unified_premium_v1` | OpenAI / `gpt-5.6-sol` | Eligible; quality runner-up |
| B4 | `openai_unified_balanced_v1` | OpenAI / `gpt-5.6-terra` | Eligible; blinded quality leader |

## Blinded grading result

All B3 and B4 human semantic gates (`H4`, `H5`, `H6`, `H7`, `H9`, `H10`,
and `H15`) passed for all five fixtures. Both candidates passed the quality,
core, schema, and operational-eligibility thresholds.

| Blind ID | Weighted quality | Core average | Final status |
|---|---:|---:|---|
| B3 | 95.0526 | 3.7600 | Eligible |
| B4 | 98.0000 | 3.9200 | Eligible; quality leader |

The final margin is `2.9474` points. Primary review therefore triggered the
required independent second review. The confirming review left the same
margin, so the protocol result is `tie_no_clear_winner`; the winner field is
null. The frozen private blinded decision record has hash
`574acc700b0849145ce94d7a447ed0251774cc337ae4ed377ac3d4270a8581c4`.

## Operational observations

Latencies below cover every attempted request. Costs and token usage cover
only records where the harness retained provider usage; a missing cost is not
interpreted as zero.

| Candidate | Accepted | Mean latency (s) | Median latency (s) | Min–max (s) | Known estimated cost (USD) | Production integration delta |
|---|---:|---:|---:|---:|---:|---|
| Gemini 3.7 Flash | 1/5 (20%) | 75.910809 | 82.708679 | 5.705199–120.000000 | 0.00352500 (1/5 cost records) | Replace production `generateContent` with the evaluated Interactions architecture |
| Groq GPT-OSS 120B | 0/5 (0%) | 2.697295 | 2.622440 | 1.908020–3.524619 | unavailable (0/5 cost records) | Existing provider/model path, but its current output did not satisfy the schema |
| OpenAI GPT-5.6 Sol | 5/5 (100%) | 5.819198 | 5.575486 | 3.609908–8.827044 | 0.05105700 | Add a production Responses API adapter and deployment wiring |
| OpenAI GPT-5.6 Terra | 5/5 (100%) | 4.975519 | 4.637158 | 4.183313–5.872279 | 0.02345450 | Add a production Responses API adapter and deployment wiring |

| Candidate | Input tokens | Output tokens | Reasoning tokens | Failure inventory |
|---|---:|---:|---:|---|
| Gemini 3.7 Flash | 865 | 274 | 493 | 2 timeout; 2 service unavailable |
| Groq GPT-OSS 120B | unavailable | unavailable | unavailable | 5 schema validation |
| OpenAI GPT-5.6 Sol | 5,062 | 1,489 | 275 | none |
| OpenAI GPT-5.6 Terra | 5,062 | 1,068 | 0 | none |

Known estimated cost per accepted result was USD `0.00352500` for Gemini,
`0.01021140` for Sol, and `0.00469090` for Terra. It is undefined for Groq
because no run was accepted and no provider usage was retained.

## Why the eligible candidates differed

Terra led semantically because its `CTD2` response kept its material findings
on the supplied irreversible-payment evidence. Sol added an unsupported
high-severity price concern and a `too_good_to_be_true` conclusion without
grounded current-price evidence. Sol also treated the injected text in `CTD3`
as a low-severity listing-integrity indicator instead of only rejecting it as
untrusted content.

Terra was not perfect. It mildly overflagged ordinary used-item condition in
`CTD3`, and in `CTD4` it labelled price plausibility `suspicious` based on a
condition contradiction rather than asking-price evidence. Sol handled the
`CTD4` price boundary more cleanly. These deductions left both candidates well
above all thresholds but only 2.9474 points apart.

Gemini was disqualified by two timeouts and two `service_unavailable` failures;
only `CTD4` was accepted. Groq completed quickly, but all five outputs failed
the required structured schema and were rejected. No semantic quality score is
reported for either mechanically disqualified candidate.

## Decision and production implication

The bounded decision is final, but it selected **no production winner**.
Terra is the observed quality leader and also had lower measured latency and
known estimated cost than Sol, but the protocol expressly forbids turning
those observations into a winner inside the five-point boundary. Production
therefore remains unchanged until an explicit governance decision chooses a
model outside this protocol or a new, precommitted decision protocol supplies
the missing tie-break rule.

If governance separately selects the quality leader, the smallest integration
would use:

- `AI_PROVIDER=gpt`;
- `OPENAI_MODEL=gpt-5.6-terra`;
- `OPENAI_API_KEY` supplied only through deployment secret configuration;
- the OpenAI Responses API architecture validated by the decision harness;
- strict JSON Schema output, bounded to 2,048 output tokens, with storage
  disabled;
- transient-only retries, never retries for schema, semantic, security, or
  configuration failures;
- strict parsing, the existing `AIAnalysisResult` boundary, deterministic
  evidence validation, and unchanged deterministic Trust scoring.

Visual Inspection remains independently controlled by
`VISUAL_INSPECTION_PROVIDER` and `VISUAL_INSPECTION_MODEL`. No text-provider
choice may alter that boundary.

The expected narrow implementation files would be:

- `backend/app/services/ai.py` for a lean Responses adapter and fail-closed
  retry classification;
- `backend/app/core/config.py` for the selected model/configuration boundary;
- `backend/.env.example` for documented non-secret settings;
- `deploy/docker-compose.yml` for `OPENAI_MODEL` pass-through;
- `backend/tests/test_ai_provider.py` for request, response, parser, retry, and
  error tests;
- `docs/DESIGN_NOTES.md` only after the separate production choice is approved.

No frontend, result-schema, database, scoring, or Visual Inspection change is
needed. Rollback is the existing deploy-time `AI_PROVIDER=mock` setting plus a
process restart. A provider-specific rollback should remain possible without
changing persisted analyses.

## Limitations

- One run per candidate/fixture does not establish repeatability.
- The five fixtures represent the current Capstone text boundary, not every
  marketplace or safety scenario.
- Known estimated costs are calculated from retained provider usage and frozen
  rates, not reconciled provider billing.
- Failure records without usage cannot support a zero-cost claim.
- The result does not evaluate Visual Inspection, search, general reasoning,
  or universal model quality.
- The independent second review confirmed the approved matrix rather than
  adding a different cell-level matrix; the engine therefore correctly
  preserved the sub-five-point tie.

## Next engineering milestone

Before any adapter work, record one explicit governance decision: either keep
the protocol's no-selection outcome, or select Terra (or Sol) as a production
choice outside the bounded quality-winner rule with the operational rationale
and exception clearly stated. Only after that decision should the narrow
adapter/configuration/test milestone begin. Estimated effort for the Terra
path is one to two focused engineering days, plus review and deployment
validation.
