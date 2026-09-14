# TrustAI AI Provider and Model Evaluation

This directory defines a controlled, provider-neutral bake-off for candidate
AI provider/model architectures. It is non-production research: no winner is
predetermined, and a result here does not alter TrustAI's runtime behavior.

## Workloads

The evaluation treats three workload families separately:

1. text risk analysis;
2. grounded current product and price research; and
3. Visual Inspection of user-supplied photos.

`fixtures.v1.json` freezes the case definitions. `rubric.v1.json` freezes the
hard gates, scoring criteria, consistency rules, and decision thresholds.
Execution-time truth sheets will capture time-sensitive search and price facts;
they are deliberately not embedded in the fixture manifest.

## Provider-visible boundary

Provider requests must be built from workload-specific allowlists in
`fixtures.v1.json`; a harness must never serialize an entire fixture object.

- Text providers receive only the title, description, asking price, currency,
  marketplace/source, applicable region, and separately versioned
  provider-neutral task instructions.
- Search providers receive only the fixed product identity, exact fixed
  variant/SKU, region, currency, fixed research objectives, and separately
  versioned provider-neutral research instructions.
- Visual providers receive only approved image bytes, sanitized listing
  context, and separately versioned provider-neutral visual instructions.

Fixture IDs, expected or forbidden conclusions, expected direction, grading
anchors, truth sheets, expected photo references, injection flags, hashes,
notes, and all ground-truth metadata are evaluator-only. They must never enter
a provider prompt or request.

Only transport-envelope unwrapping and deterministic representation
normalization are permitted. Normalization must never add missing semantic
fields, alter an answer, remove forbidden semantic output, invent a source, or
hide a refusal or malformed result. Both raw and normalized hashes and the
normalizer version are recorded.

## Experimental rules

- Record the exact fixture and rubric versions for every run.
- A hard-gate failure overrides the quality score.
- Blind provider identity during human grading where practical.
- Give candidates semantically equivalent instructions and evidence, while
  allowing provider-appropriate call topology.
- Preserve every attempt, including malformed, failed, and retried attempts.
- Record the exact provider, model, model version or snapshot, configuration,
  tool use, timing, and usage for every run.
- Normalize results to TrustAI's evaluation contracts before comparing them;
  do not score provider-specific response envelopes.
- Never commit credentials or raw provider responses. Review and sanitize any
  retained research output before it is shared.
- Use only synthetic, team-owned, non-sensitive visual assets with recorded
  provenance.
- Run preflight once for every candidate before any provider result is seen. A
  failed fixture pauses the experiment; it is never dropped or substituted for
  only one candidate.
- Report hard gates, raw workload and criterion scores, the weighted
  architecture score, and a small weight-sensitivity analysis. Never report
  only the weighted total.

## Experiment phases and change control

Pilot runs verify transport, schema integration, records, and likely cost.
They are labeled as pilot, never enter comparative scores, and cannot later be
promoted into scored results. Methodology may change after a pilot only before
the scored experiment version is frozen.

The fixture manifest, rubric, truth sheet, visual asset set, prompt templates,
and harness each have an explicit version. Once the first scored provider call
occurs, that experiment version is immutable. A material change starts a new
experiment version; prior attempts and results remain preserved.

Baseline planned runs form the comparative score. Ten-run diagnostics are
exploratory and do not alter the original score unless every candidate is
rerun under a newly declared common protocol and experiment version.

## Human grading

Before scored grading, two blinded graders jointly calibrate on three anchor
examples using criterion-specific 0–4 descriptions, then grade independently.
A third grader adjudicates hard-gate disagreements and criterion differences
of two or more points. Original grades and the adjudicated result are retained.

## Source and production eligibility

Source authority is claim-dependent, not a universal ranking. Manufacturer
sources support identity, specifications, MSRP, direct availability, and
manufacturer offers; retailers support their own offers and stock; active
marketplace listings support asking-price evidence; completed transactions
support condition-matched comparables. Secondary sources may clarify context,
while forums, social posts, affiliate pages, SEO pages, and aggregators are
discovery leads unless their underlying evidence is retrieved.

No candidate may be proposed for production until its API data-use policy,
retention and abuse-monitoring behavior, user-photo handling, credential
governance, and relevant regional/legal constraints have been reviewed and
found acceptable. This architecture-eligibility review is separate from the
H1–H18 per-run output gates.

## Current status

This is the specification phase only. No credentialed evaluation has occurred,
no provider or model has been selected, and no production change or deployment
is implied.
