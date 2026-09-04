# TrustAI Marketplace - Final Presentation Runbook

## Status, purpose, and authority

**Status:** READY WITH CONFIRMATIONS for team rehearsal. This runbook is not
evidence that the presentation has been recorded, hosted, or submitted.

This is the rehearsal-ready source of truth for the final Quantic MSSE
Capstone presentation. It targets a clear, natural **17:30** group recording
that demonstrates the released product, explains the most important
engineering decisions, and stays inside the verified evidence boundary.

| Presentation identity | Value |
|---|---|
| Product | TrustAI Marketplace |
| Final release | `v1.20.0` |
| Immutable release commit | `5ebc757ba66ff647944602245c18bedf6631680e` |
| Production application | [https://trustai.mandalawi.ca](https://trustai.mandalawi.ca) |
| Target duration | 17:30 |
| Rehearsal band | 17:00-18:00 |
| Required final duration | 15:00-20:00 |
| Recording format | One video; MP4 strongly recommended, MOV accepted |
| Submission state | **OPEN** |

The source hierarchy for this runbook is:

1. the [Handbook requirements index](HANDBOOK_REQUIREMENTS_INDEX.md) for
   presentation and submission controls;
2. release `v1.20.0` source and the
   [final production validation](FINAL_PRODUCTION_VALIDATION.md) for current
   product behavior;
3. the [design and testing report](CAPSTONE_DESIGN_AND_TESTING.md) for the
   current architecture and engineering rationale; and
4. the [meeting](meetings/README.md), [sprint](sprints/README.md), Trello, and
   Git/PR records for team/process chronology.

A plan proves intent, source proves implementation, a release identifies
immutable source, deployment health proves only its configured health path,
and the September 4 browser record proves only the live behavior it actually
observed. Old plans do not override the final implementation, and the final
implementation does not rewrite project history.

## Handbook controls

The final recording must satisfy all of these controls:

- one recorded presentation with screen capture and voiceover;
- every final group member is present, speaks, and is visible/on camera;
- every presenter briefly shows a government-issued ID with name and photo
  clearly legible;
- the team summarizes the solution and demonstrates the functional
  capabilities of the deployed system;
- the recording is between 15 and 20 minutes;
- one MP4 is strongly recommended; one MOV is also accepted;
- the final file is hosted on Google Drive with **Anyone with the link can
  view**; and
- one designated team member submits it through Quantic.

The Handbook does **not** add a slide requirement, Q&A requirement,
continuous-face requirement, unedited-take requirement, or filename rule.
Slides may support the demonstration, but they cannot replace the one video.

## Presenter roster and contribution basis

The final team roster is authoritatively confirmed as exactly five members.
Historical planning and meeting records use shortened or variant forms of
three names; the official presenter names below govern the final recording,
identity checks, captions, and submission materials. Speaker assignments
follow the strongest meeting and Git/PR evidence rather than Trello membership
alone.

| Presenter | Verified project role | Evidence-backed contribution areas | Presentation ownership |
|---|---|---|---|
| Ahmed Al-Mandalawi | Product Owner / AI Analysis Lead | Product direction, core AI analysis, evidence boundaries, HTTPS/release integration, Visual Inspection, strict Terra integration, final validation | Opening, live text analysis, model/limitation framing, close |
| Mulima Chibuye | Project Manager / Scrum Master | Sprint coordination; auth/profile; scoring; price plausibility; provider abstraction; history and failed-listing recovery | Contrasting cases, History/recovery, Agile/process |
| Rangarirai Revivalist Nyamadzawo | Backend Lead - Auth, Listings & Data | API/data foundation, migrations, release automation, contract/integration tests, account deletion, URL extraction, admin analytics, operational hardening | Deterministic score/validation, architecture/security |
| Adrin Kudakwashe Muchatibaya | Frontend Lead | Wireframes, React application structure, authentication/listing forms, landing/history integration, UI review corrections | User journey, Visual interaction, responsive/theme behavior |
| Samar Salah Elghandour | QA & DevOps Lead | Branch/review controls, ECR/EC2 deployment, SSM delivery, CI/CD architecture and release-quality work | Testing, CI/CD, immutable deployment |

### Confirm before recording

- Use the five confirmed official names above exactly in the recording,
  captions, and submission materials.
- Locate the final Group Project Agreement and verify that it lists these five
  members and contains every required signature. The roster is confirmed, but
  the Agreement itself has not yet been received or verified.
- Confirm every member accepts the contribution summary and assigned segment.
- Confirm all five can remain present and visible for the complete recording.
- Do not include Abdallah Mohmoud in the final roster. He attended the July 1
  kickoff, but the July 8 record says the project proceeded with five active
  members after he did not continue.

If the signed agreement does not match the confirmed roster, stop and resolve
the contradiction before recording or submission. Do not improvise a roster
change during the recording.

## Story arc

The presentation follows one argument:

1. Marketplace listings contain incomplete and sometimes contradictory
   evidence.
2. TrustAI turns buyer-supplied listing content into structured decision
   support, not a legitimacy guarantee.
3. The deployed journey combines editable listing input, bounded AI analysis,
   deterministic application scoring, History, recovery, and optional Visual
   evidence.
4. The architecture keeps untrusted provider output behind strict contracts
   and keeps the Visual channel separate from the text score.
5. Automated quality gates and immutable deployment connect reviewed source to
   the released product.
6. The team explains what is verified, what is intentionally bounded, and what
   remains future work.

## Exact 17:30 timing plan

| Time | Sec. | Presenter | Screen and action | Core talking points | Rubric purpose | Fallback / cut priority |
|---|---:|---|---|---|---|---|
| 0:00-1:15 | 75 | All five, 15 seconds each | Camera/gallery; no shared application yet | Name, role, brief government-ID check | Presence, identity, visibility, audibility | Never cut; pause for focus rather than rushing |
| 1:15-2:15 | 60 | Ahmed Al-Mandalawi | Production landing page | Buyer uncertainty; decision support; listing to structured guidance; no legitimacy guarantee | Clear problem and solution | Keep at least 45 seconds |
| 2:15-3:25 | 70 | Adrin Kudakwashe Muchatibaya | Authenticated form in light mode | Registration/sign-in journey; manual entry; URL preview as editable suggestion; responsive interface | User-story breadth and deployed UI | Use saved landing/form view if session expires |
| 3:25-4:45 | 80 | Ahmed Al-Mandalawi | Submit Case A live; explain result | Low risk, Trust 4, Plausible, Buy; indicators, questions, limitations; Terra label; score is application-owned | Live correct operation and explainability | Use pre-seeded Case A if slow/fails; do not fake live success |
| 4:45-6:25 | 100 | Rangarirai Revivalist Nyamadzawo | Stay on Case A result/gauge | Strict provider-output boundary; categorical consistency; deterministic 0-100 score, not fraud probability | Design rationale and correctness | Verbal with result visible |
| 6:25-7:40 | 75 | Mulima Chibuye | Open saved Case B, then optional Case C | Contrast high-risk evidence with recent-product uncertainty; current price not verified | Range of inputs | Case C is first cut; Case B remains |
| 7:40-8:40 | 60 | Mulima Chibuye | History, newest first; reopen an item; point to Account controls | Persistence and ownership; failed listing is recoverable; account controls exist | Functional breadth and resilience | Recovery is verbal/test evidence only; never force an outage |
| 8:40-10:20 | 100 | Adrin Kudakwashe Muchatibaya | Open saved Case C; Visual pre-state, consent, upload synthetic PV1 | Separate advisory photo channel; `DEMO UNIT` visible-text observation; unchanged text result | Visual capability, consent, privacy boundary | Use sanitized fallback evidence if slow/fails |
| 10:20-10:45 | 25 | Adrin Kudakwashe Muchatibaya | Quick theme toggle and narrow viewport only if rehearsed | Light/dark/system-start behavior and responsive layout | UI range and professional presentation | First whole segment to cut if late |
| 10:45-12:20 | 95 | Rangarirai Revivalist Nyamadzawo | Current architecture visual | React/FastAPI/PostgreSQL; Caddy/nginx; provider boundary; SSRF/auth/ownership; Visual isolation | Architecture and security | Use static current diagram; never use plan-era microservices as final |
| 12:20-13:45 | 85 | Samar Salah Elghandour | Preloaded test/release evidence | Test layers, failure boundaries, and exact immutable release results | Testing strategy and demonstrated quality | Static evidence; state exact results without enumerating every test area |
| 13:45-15:35 | 110 | Samar Salah Elghandour | Continue on CI/release/deployment evidence | PR controls; semantic release; ECR/EC2/SSM; immutable images; health-check scope and live-validation distinction | Collaboration, delivery, and operational evidence | No live workflow execution; shorten implementation detail before cutting evidence boundaries |
| 15:35-16:35 | 60 | Mulima Chibuye | Current app or sanitized board overview | Planned sprints, real carryover, Trello/Git/PR coordination, role accountability, honest evidence gaps | Agile/team process | Verbal over app if board access or privacy is risky |
| 16:35-17:10 | 35 | Ahmed Al-Mandalawi | Return to result or landing page | Model-selection decision; limits and future work: no guarantee, no verified live price, Visual advisory, backup/runtime switching deferred | Evidence-based choice and honest boundaries | Keep the four core limitation claims; remove secondary examples if late |
| 17:10-17:30 | 20 | Ahmed Al-Mandalawi | Closing application screen | Deployed user value; structured and explainable guidance; evidence-driven team outcome | Concise professional close | Never cut |

### Timing arithmetic

`75 + 60 + 70 + 80 + 100 + 75 + 60 + 100 + 25 + 95 + 85 + 110 + 60 + 35 + 20 = 1,050 seconds = 17:30.`

| Presenter | ID seconds | Owned-section seconds | Total | Total time |
|---|---:|---:|---:|---:|
| Ahmed Al-Mandalawi | 15 | 195 | 210 | 3:30 |
| Mulima Chibuye | 15 | 195 | 210 | 3:30 |
| Rangarirai Revivalist Nyamadzawo | 15 | 195 | 210 | 3:30 |
| Adrin Kudakwashe Muchatibaya | 15 | 195 | 210 | 3:30 |
| Samar Salah Elghandour | 15 | 195 | 210 | 3:30 |
| **Total** | **75** | **975** | **1,050** | **17:30** |

Every member owns 3:15 of substantive content in addition to the 15-second ID
check. The balanced allocation comes from compressing repeated product
narration and giving the documented backend-validation, testing, release, and
delivery responsibilities their own explanation time; it does not assign any
presenter work outside the verified contribution record.

## Recording roles and setup

Assign these operational roles before the dress rehearsal:

| Recording role | Responsibility | Confirmed owner |
|---|---|---|
| Recording owner | Starts/stops capture, confirms gallery + screen are captured, preserves master file | **CONFIRM** |
| Primary screen controller | Runs the production browser sequence without shared-control handoffs | **CONFIRM**; Ahmed Al-Mandalawi is the practical default |
| Timekeeper | Gives silent 7:40, 12:20, 16:35, and 18:30 signals | **CONFIRM** |
| Fallback controller | Opens prepared sanitized evidence if the live app stalls | **CONFIRM** |
| Final QA owner | Watches the full export and completes the post-recording checklist | **CONFIRM** |
| Quantic submitter | Performs the one group submission after all access checks | **CONFIRM** |

Prefer one screen controller for the whole demo. Speaker handoffs do not need
screen-control handoffs.

### Presentation-safe browser state

- Share the application browser window or tab, not the entire desktop.
- Use [the production application](https://trustai.mandalawi.ca) in light mode
  at a rehearsed, readable zoom.
- Use only the authorized non-personal demo account. Confirm the visible name
  and email are presentation-safe before screen sharing.
- Keep the session authenticated, but preserve a sanitized landing/auth image
  as fallback. Do not expose cookies, session storage, tokens, headers, or
  developer tools.
- Close unrelated tabs, password managers, email, chat, notifications, and
  personal file windows. Enable Do Not Disturb.
- Preload only: production app, the current architecture visual, the immutable
  CI/release evidence, and sanitized fallbacks.
- Keep Case B and Case C pre-seeded in History. Confirm their displayed values
  immediately before recording.
- Put the approved synthetic PV1 image in a presentation-only folder with no
  personal filenames nearby. The image is a 640x480 generic drawing containing
  `DEMO UNIT`; it must contain no person or personal data.
- Never show a credential, `.env`, provider dashboard, private host, raw
  provider response, database row, or terminal containing operational values.
- Have a separate timer that is not captured.

## Government-ID opening procedure

Use gallery view. The recording owner calls each presenter in the final order:
Ahmed Al-Mandalawi, Mulima Chibuye, Rangarirai Revivalist Nyamadzawo, Adrin
Kudakwashe Muchatibaya, and Samar Salah Elghandour. Each has 15 seconds:

1. state full name and project role;
2. hold the government-issued ID close enough for the name and photo to focus;
3. cover unrelated information if that does not obstruct the required name or
   photo; and
4. wait for a silent focus confirmation before lowering it.

Do not read or discuss the ID number, date of birth, address, signature, or
other unrelated fields. If the name/photo is not legible, pause and repeat that
presenter's check. Do not continue and hope post-production will fix it.

## Detailed demonstration plan

### Safe synthetic cases

These inputs are synthetic and contain no real seller identity, contact detail,
address, credential, or verified-live-price claim.

#### Case A - benign / low-risk - LIVE

| Field | Value |
|---|---|
| Title | Logitech MX Master 3S Wireless Mouse |
| Price | 74.99 |
| Currency | USD |
| Source | Synthetic Marketplace Demo |
| URL | Leave blank |
| Description | Synthetic demo listing. Logitech MX Master 3S wireless mouse in graphite. Seller says it is lightly used, includes the Logi Bolt receiver and charging cable, offers inspection at a public meeting place, and accepts payment only after inspection. No urgency or off-platform payment request. |

September 4 observed result: `low`, Trust score `4`, `Plausible`, `Buy`,
approximately four seconds, and `Model used: gpt-5.6-terra`.

**Live action**

1. Briefly point out manual fields and the optional **Fetch details** path.
   Explain that URL preview returns editable suggestions; it does not bypass
   validation or independently verify the listing.
2. Submit Case A once. Do not repeatedly click.
3. While waiting, explain that provider output is not accepted until strict
   parsing, schema, cross-field, and evidence-policy checks pass.
4. On success, show the risk badge, Trust gauge, price-plausibility badge,
   recommendation, indicators, seller questions, limitations, and model label.
5. Say: **“The model supplies structured categories and explanations. The
   application computes the Trust score deterministically after validation; it
   is not a model-generated probability of fraud.”**

The displayed result is authoritative for the recording. Do not announce the
expected `4` before it renders. If it differs from the earlier synthetic
observation but remains coherent, describe what is actually on screen. If it
is slow, fails, or violates the expected contract, move to the saved Case A
fallback and state that the live attempt did not complete; never imply it did.

#### Case B - suspicious / high-risk - SAVED

| Field | Value |
|---|---|
| Title | Brand-new MacBook Pro M4 Max 1TB |
| Price | 350 |
| Currency | USD |
| Source | Synthetic Marketplace Demo |
| Description | Synthetic demo listing. Seller says the laptop is brand new but cannot provide a serial number or receipt, insists on cryptocurrency prepayment, refuses collection or video proof, claims to be leaving today, and says another buyer will take it within ten minutes. The listing alternates between 14-inch and 16-inch and says shipping only. |

Verified saved result: `high`, Trust score `100`, `Too good to be true`,
`Avoid`.

Open the saved result. Point to the supplied evidence: irreversible advance
payment, urgency, refusal of inspection/proof, and contradictory dimensions.
Do not say the product or seller was proven fraudulent. The correct claim is
that the listing contains multiple explicit risk signals and TrustAI recommends
avoiding the transaction.

#### Case C - recent-product / knowledge boundary - SAVED, OPTIONAL

| Field | Value |
|---|---|
| Title | Nintendo Switch 2 Mario Kart World Bundle |
| Price | 429 |
| Currency | USD |
| Source | Synthetic Marketplace Demo |
| Description | Synthetic demo listing for a recently released product. Seller describes a lightly used Nintendo Switch 2 Mario Kart World bundle with the console, dock, Joy-Con controllers, charging cable, retail box, and purchase receipt. Seller offers an in-person inspection and payment after testing. The listing provides no independently verified current market price. |

Verified saved result: `low`, Trust score `4`, `Plausible`, `Buy`.

Use Case C only if timing allows. The point is not that the current market price
was verified; it was not. The point is that uncertainty about a recent product
is not itself converted into an adverse fraud signal. If the presentation is
late, skip this text comparison and use Case C only as the host analysis for
Visual Inspection.

#### Case D - internal contradiction - FALLBACK ONLY

| Field | Value |
|---|---|
| Title | Canon EOS R8 Camera Kit |
| Price | 900 |
| Currency | USD |
| Source | Synthetic Marketplace Demo |
| Description | Synthetic demo listing. The title says the camera includes a lens, but the description later says body only. It first says the battery and charger are included, then says the buyer must supply both. Seller offers an in-person inspection and payment after testing, with no urgency or advance-payment request. |

Case D was not live-executed during the September 4 validation. Use it only as
a prepared input/fallback explanation of supplied-field contradiction. Do not
present an expected output as observed fact.

### History, recovery, and account controls

In History:

1. show the new Case A at the top after its live completion;
2. show that saved results are newest-first;
3. reopen Case B or Case C and confirm the structured result remains available;
4. point out that history is owner-scoped; and
5. open Account only if the authorized demo profile is presentation-safe.

Registration, sign-in, profile update, account deletion, session expiry, and
sign-out are implemented. Do not delete or modify the only demo account during
the recording. The authenticated session plus prepared landing/account views
are the reliable presentation method.

Failed-listing recovery is implemented and tested: a listing is stored before
analysis, appears in the failed-listing area after an analysis failure, and can
be retried without retyping it. The September 4 browser validation did not
force that failure path. Explain it verbally with test/source evidence. Never
trigger an outage or provider failure for the presentation and never call it a
live-exercised result.

### Visual Inspection - LIVE WITH FALLBACK

Use the saved Case C analysis and the approved synthetic PV1 image.

1. Show the existing text result before Visual: Trust `4`, risk `low`,
   recommendation `Buy`, price plausibility `Plausible`.
2. Show that **Inspect photos** is disabled before fresh consent.
3. Select only PV1. Confirm the file picker exposes no personal filenames.
4. Read the concise disclosure: the photo goes to OpenAI for processing;
   provider handling follows the applicable provider policy.
5. Select the consent checkbox and submit once.
6. On success, show the photo-grounded `DEMO UNIT` visible-text observation and
   its Photo 1 reference.
7. Return to the unchanged text result fields. State: **“Visual Inspection is a
   separate advisory channel. It does not change the Trust score, risk level,
   price-plausibility result, or recommendation.”**
8. If time allows, navigate to History and reopen Case C to show that the text
   result persists while the Visual finding does not and a fresh upload form
   appears.

The September 4 controlled validation established this application behavior
and identified OpenAI as the photo recipient in the UI. It did **not** expose
the exact Visual model. Do not name one. Photos and findings are not persisted
by the TrustAI application; do not claim zero provider retention.

If Visual is slow or fails, stop waiting at the rehearsed threshold, show the
sanitized fallback captured during the technical rehearsal, state that the
live request did not complete, and continue. Do not resubmit during the final
recording.

### Theme and responsive behavior

Light mode is recommended for projection and recording. If on time, toggle
light to dark and back once, or briefly show a rehearsed narrow browser view.
State only what is implemented: the app initially follows the operating-system
preference when no choice is stored, then preserves an explicit light/dark
choice. Do not spend time claiming a three-choice theme selector.

The September 4 browser check found no horizontal overflow in the authenticated
form, result, History, navigation, or Visual areas at desktop and a 390x844
viewport override. That was a manual browser observation, not an automated
Playwright suite.

## User-story coverage matrix

| Capability | Method | Presenter | Sec. | Evidence boundary |
|---|---|---:|---:|---|
| Registration / sign-in / sign-out / session | SAVED + authenticated LIVE shell + VERBAL | Adrin Kudakwashe Muchatibaya | 15 | Released source/tests; authenticated session observed; do not sign out and risk the demo |
| Profile and account deletion controls | LIVE view + VERBAL | Mulima Chibuye | 8 | Controls implemented; do not edit/delete demo account |
| Manual listing submission | LIVE | Ahmed Al-Mandalawi | 35 | Case A through production UI |
| URL preview | LIVE control shown + VERBAL | Adrin Kudakwashe Muchatibaya | 12 | Best-effort editable suggestion; no arbitrary external fetch during recording |
| Structured analysis | LIVE | Ahmed Al-Mandalawi | 55 | Case A result |
| Deterministic Trust score | LIVE result + VERBAL | Rangarirai Revivalist Nyamadzawo | 35 | Application-owned formula; not a probability |
| Risk / recommendation / price plausibility | LIVE + SAVED contrast | Ahmed Al-Mandalawi / Mulima Chibuye | 65 | Case A and B; Case C optional |
| Indicators, questions, limitations | LIVE | Ahmed Al-Mandalawi | 30 | Case A result |
| History newest-first / reopen | LIVE | Mulima Chibuye | 30 | September 4 path already observed |
| Failed-listing recovery | VERBAL / TEST EVIDENCE | Mulima Chibuye | 12 | Do not force production failure |
| Per-listing retry isolation | VERBAL / TEST EVIDENCE | Mulima Chibuye | 5 | Released frontend behavior |
| Visual availability / consent / findings | LIVE WITH FALLBACK | Adrin Kudakwashe Muchatibaya | 70 | One synthetic PV1 request maximum in the recording |
| Visual score separation / transience | LIVE WITH FALLBACK | Adrin Kudakwashe Muchatibaya | 25 | Application-level only; provider policy remains separate |
| Responsive layout and themes | OPTIONAL LIVE | Adrin Kudakwashe Muchatibaya | 25 | First cut if late |
| Admin aggregate analytics | VERBAL ONLY if needed | Rangarirai Revivalist Nyamadzawo | 5 | Implemented endpoint; no safe admin demo account established |

`LIVE` means performed in the final recording. `SAVED` means an authentic
pre-seeded result from the deployed app. `VERBAL / TEST EVIDENCE` means the
feature is released but is not intentionally exercised in production during
the recording. Do not relabel these methods after the fact.

## Architecture and design section

Use the current diagram in
[the design and testing report](CAPSTONE_DESIGN_AND_TESTING.md#3-final-system-architecture)
or a directly derived, legible visual. Do not use the early Render/Groq or
microservices diagrams as the final architecture.

### Architecture in 95 seconds

- The browser runs React/JavaScript built with Vite.
- Caddy terminates public HTTPS; nginx serves the frontend and proxies `/api`.
- FastAPI and Pydantic own HTTP contracts and validation.
- SQLAlchemy/Alembic persist user-owned listing and text-analysis history in
  PostgreSQL.
- Text providers sit behind one `AIProvider` boundary. When the `gpt` provider
  is selected, the released OpenAI source path uses Responses and prompt `v4`,
  with Terra as its default model.
- Visual Inspection is configured independently and intentionally has no
  persistence table or scoring path.
- GitHub Actions publishes immutable commit-SHA images to ECR and activates
  them on EC2 through SSM.

### Strongest decisions: decision -> reason -> benefit

1. **Provider abstraction.** External protocols vary, so adapters translate
   them into one application contract. Tests can stay deterministic and the
   public API does not depend on one wire format.
2. **Strict generated-output validation.** Model output is untrusted, so UTF-8
   JSON parsing, exact schemas, cross-field rules, and evidence policies run
   before persistence. Nearly correct output fails closed instead of being
   silently repaired.
3. **Deterministic scoring.** A model-generated number would be uncalibrated,
   so the server computes 0-100 from validated risk categories and severities.
   The score cannot contradict low/medium/high.
4. **Visual isolation and privacy.** Image evidence has a different consent,
   provenance, and lifecycle boundary, so it stays advisory and transient in
   the TrustAI application rather than changing the text result.
5. **Persist-before-analyze and recovery.** Provider failure should not erase
   user input, so the listing is retained and can be retried safely.

### Model-selection story in 20 seconds

The frozen comparison produced **TIE / NO CLEAR WINNER** under its own rule:
Terra's quality score of `98.0000` led Sol's `95.0526` by `2.9474`, below the
strict greater-than-five-point winner threshold. The team then made a separate
production engineering decision to select Terra for this Capstone workload,
using its observed quality lead and 5/5 first-attempt acceptance together with
lower observed mean latency (about 4.9755 seconds versus 5.8192) and lower
five-call estimated cost (USD 0.02345450 versus USD 0.05105700). Say that Terra
was selected; do not say it formally won the protocol or is universally the
best model.

If security is mentioned, use concrete controls: authenticated owner-scoped
queries, bcrypt hashes, expiring JWT sessions, bounded SSRF-aware URL preview,
strict provider boundaries, normalized image inputs, aggregate-only admin
analytics, environment-held secrets, and SSM deployment. Do not claim perfect
security. CORS hardening, expanded auth, backup recovery, and automated browser
E2E remain limitations.

## Testing, CI/CD, and release section

### Testing evidence in 85 seconds

Samar Salah Elghandour should use these exact immutable `v1.20.0` results:

- contract selection: **70 passed, 379 deselected, 8 warnings**;
- complete backend: **449 passed, 140 warnings**;
- backend coverage: **96.49%**, above the **85%** gate;
- frontend: **76 tests passed across 9 files**; and
- production build: **passed, 39 modules transformed**.

Explain why the layers exist, not only the totals:

- unit tests isolate security, schemas, scoring, and policies;
- API/integration tests exercise auth, ownership, persistence, history, and
  failure recovery across requests;
- contract/provider-boundary tests reject malformed or unsafe generated data
  and verify bounded failure behavior without live provider requests;
- frontend tests cover API call sites, session expiry, retry isolation,
  consent, capability hiding, themes, and result rendering; and
- the build catches bundling/import failures that component tests may miss.

Do not claim automated browser E2E. Frontend tests use jsdom, backend tests
principally use SQLite, and provider tests use mocked transports. CI/provider
tests require no provider credentials and make no live provider requests.

### CI/CD and release in 110 seconds

For delivery, say that pull requests run required CI and current-head review
controls, semantic-release creates versioned immutable source, GitHub Actions
builds SHA-tagged backend/frontend images, and SSM activates them on EC2 without
inbound SSH. The deployment gate's container-local request traverses Caddy,
nginx, and FastAPI. It does not alone prove public DNS/TLS/browser/provider
behavior; the separate September 4 browser record supplies the live
application evidence.

## Agile and team section

Use the project chronology honestly:

- July 1 selected TrustAI and assigned Ahmed as Product Owner and Mulima as
  Scrum Master.
- July 8 established five active members, planned Sprint 0 plus three build
  sprints, chose Trello, and assigned workstream accountability.
- Delivery crossed planned sprint boundaries. July/August meetings record
  integration pressure, Trello drift, and a recovery plan rather than perfect
  Scrum execution.
- Git, pull requests, reviews, CI, releases, and deployment establish
  engineering activity. They do not prove a meeting occurred.
- The final Trello state was reconciled against `v1.20.0`; late reconciliation
  does not recreate historical card-movement dates.
- The dedicated sprint-end application-demo recordings required by the
  Handbook have not been verified. Do not present meetings or rehearsals as
  substitutes.
- The team used role accountability with cross-boundary pairing rather than
  isolated ownership.

Natural transition from Mulima to Ahmed:

> “Our original plan gave us a direction, but the delivery record also shows
> where integration and release work crossed sprint boundaries. We kept those
> gaps visible and used the final release evidence to decide what we could
> claim. Ahmed will close with the boundaries that follow from that approach.”

## Speaker handoffs and talking-point cards

These are prompts, not a word-for-word script.

| Speaker | Handoff in | Talking-point card | Natural handoff out | Screen controller |
|---|---|---|---|---|
| Ahmed Al-Mandalawi | After ID checks; later from Adrin and Mulima | Buyer uncertainty; decision support; evidence boundary; Case A; final limitations/value | “Adrin will show how that journey begins in the interface.” / after Case A: “Rangarirai will show why the score is repeatable.” | Primary controller |
| Adrin Kudakwashe Muchatibaya | From Ahmed for the form; later from Mulima for Visual | Auth/listing flow; editable preview; consented Visual; mobile/theme | After the form: “Ahmed will now run the benign case.” / after Visual: “Rangarirai will show the architecture behind these boundaries.” | Primary controller continues |
| Rangarirai Revivalist Nyamadzawo | From Ahmed for score/validation; later from Adrin for architecture | Deterministic score; strict validation; final modular architecture; auth/SSRF boundaries | After the result: “Mulima will contrast this with the suspicious case.” / after architecture: “Samar will show how we tested and released it.” | Primary controller continues |
| Samar Salah Elghandour | From Rangarirai | Test layers; exact release results; reviews; release; ECR/EC2/SSM; health-check boundary | “Mulima will connect that delivery record back to how the team planned and adapted.” | Primary controller continues |
| Mulima Chibuye | From Rangarirai for cases/History; later from Samar for process | B/C contrast; History/recovery; planned sprints; real carryover; Trello/process limits | After History: “Adrin will show the separate Visual channel.” / after process: “Ahmed will close with what TrustAI does, and just as importantly, what it does not claim.” | Primary controller continues |

Backups: Ahmed Al-Mandalawi can deliver the product/AI segments; Rangarirai
Revivalist Nyamadzawo can cover architecture/testing; Mulima Chibuye can cover
process/history; Adrin Kudakwashe Muchatibaya can cover the frontend/Visual
interaction; Samar Salah Elghandour can cover CI/CD. A backup does not remove
the absent member's Handbook obligation to be present, visible, and speak. If a
member cannot attend, do not record the final submission until the team has a
compliant plan.

## Screen and asset sequence

| Order | Screen / asset | Preload and expected state | Privacy check | Controller |
|---:|---|---|---|---|
| 1 | Gallery/camera | All five cameras and IDs ready | No private room details or unrelated ID data visible | Recording owner |
| 2 | Production landing | HTTPS loaded, light mode, readable zoom | No autofill/password popup | Primary controller |
| 3 | Authenticated listing form | Demo session active; Case A text ready in a presentation-safe note | No token/devtools/private tabs | Primary controller |
| 4 | Case A result | Live result or authentic saved fallback | No raw provider body | Primary controller |
| 5 | History / Case B | B and C pre-seeded, newest-first list healthy | Synthetic titles only | Primary controller |
| 6 | Optional Case C | Saved recent-product result | Do not claim verified price | Primary controller |
| 7 | Visual on Case C | PV1 in presentation-only folder; consent initially clear | File chooser exposes no personal filenames | Primary controller |
| 8 | Current architecture visual | Final AWS modular-monolith diagram at readable zoom | No `.env`, account IDs, or private host details | Primary controller |
| 9 | CI/release evidence | Immutable `v1.20.0` run summary preloaded | No Actions secret/settings pages | Primary controller |
| 10 | Closing application screen | Clean result or landing page | No notification or personal account field | Primary controller |

Use only current/qualified architecture material. Render and microservices are
historical design evidence, not the final deployed architecture.

## Fallback matrix

| Failure | Immediate action | Fallback | Natural wording | Stop/restart? |
|---|---|---|---|---|
| Production unavailable before recording | Do not start final take | Wait or reschedule after confirming service health | Not applicable on recording | **Stop**; do not submit a demo with no deployed system |
| Production becomes unavailable mid-recording | Stop repeated clicks; note actual state | Use sanitized same-release fallback evidence and continue architecture/process | “The live service stopped responding, so we’ll use the result captured in our technical rehearsal and keep that distinction clear.” | Continue only if required capabilities remain honestly demonstrable; otherwise re-record |
| Session expired | One normal return to sign-in only | Saved authenticated screenshots; re-authenticate off-record | “Our session expired as designed; we’ll resume from the prepared authenticated state.” | Prefer **restart** after off-record recovery |
| Case A slow | Continue narration to rehearsed threshold | Open authentic saved Case A | “This request is still pending, so I’ll use the saved result from our production validation.” | Continue; never submit again in the same take |
| Case A fails | Show safe error briefly; do not force retry | Saved Case A | “The live analysis did not complete. This saved production result is our fallback; we are not presenting the failed attempt as a success.” | Continue if time and fallback are strong; consider re-record |
| History unavailable | Do not refresh repeatedly | Sanitized history capture and source/test explanation | “History is not available in this take, so this is the verified saved-state fallback.” | Continue, then assess re-record |
| Visual slow/fails | Do not resubmit | Sanitized Visual success capture from technical rehearsal | “The live Visual request did not complete; this is the earlier synthetic production result.” | Continue; one attempt only; consider re-record |
| Screen share fails | Stop narration after a brief warning | Fallback controller shares prepared window | “We’re switching to our prepared display now.” | Pause timer if editing is allowed; otherwise restart if delay is material |
| Audio failure | Timekeeper signals immediately | Fix device and repeat affected segment | No spoken workaround without audio | **Restart** if required speech was inaudible |
| Video/camera failure | Timekeeper signals; presenter reconnects | Restore gallery and repeat ID/speech as needed | “We’ll pause while the presenter restores video.” | **Restart** if member visibility cannot be verified |
| ID does not focus | Keep presenter on camera | Repeat only that ID check | “We’ll hold for focus so the required name and photo are legible.” | Continue after confirmed; re-record if final export is illegible |
| Member disconnects | Stop that member's section | Reconnect before continuing | “We’ll pause and resume with the full team present.” | **Restart** if presence/speech requirement is not clearly met |
| Running beyond 18:30 | Timekeeper sends cut signal | Skip theme/mobile; skip Case C comparison; shorten architecture examples | No announcement needed | Continue with cut sequence; never exceed 20:00 |
| Running below 15:30 near close | Add prepared Case C or fuller decision rationale | Use already rehearsed content only | “One useful contrast is how we handle a recent product without treating uncertainty as fraud.” | Continue; do not invent a new live test |

Never fabricate success, hide a visible failure, force provider failure, or
turn a prepared screenshot into a claim that the action happened live.

## Cut-first sequence

If the timekeeper signals late, cut in this order:

1. the 30-second responsive/theme segment;
2. the optional Case C text comparison (retain Case C only for Visual);
3. detailed enumeration of architecture components after the five decisions
   are clear;
4. extra CI/CD implementation detail after the exact results and immutable
   release path are stated; and
5. secondary future-work examples, retaining the four core limitation claims.

Never cut a member's substantive participation, ID, Case A, Case B, History,
Visual or its fallback, current architecture, exact test evidence, core Agile
chronology, limitations, or close.

## Presenter warning box

> **Do not claim any of the following:**
>
> - TrustAI guarantees that a listing, seller, or transaction is legitimate.
> - TrustAI verifies a live/current market price or performs comprehensive
>   market research.
> - The language model generates the numeric Trust score.
> - Visual Inspection changes the Trust score, risk level, price plausibility,
>   or recommendation.
> - Visual photos/findings have zero provider retention. The accurate claim is
>   that they are not persisted by the TrustAI application; provider handling
>   follows the applicable policy.
> - The exact Visual model was verified in the September 4 browser session.
> - Private production transport or environment values were inspected.
> - Failed-listing recovery was forced and observed live on September 4.
> - Automated browser E2E, load testing, or PostgreSQL integration tests exist
>   when the recorded release evidence does not establish them.
> - The early Render or microservices plan is the final deployment.
> - Every sprint had a verified dedicated demo recording, every ceremony was
>   preserved, or Trello was perfectly current throughout delivery.
> - Backup/restore, runtime provider switching, password reset, email
>   verification, MFA, FX normalization, grader access, agreement signatures,
>   video hosting, or final submission is complete before it is verified.

## Limitations and closing language

Use concise boundaries, not apologies:

- **Decision support:** “TrustAI helps a buyer structure the evidence and the
  next questions. It does not guarantee legitimacy or a safe transaction.”
- **Price:** “Price plausibility is qualitative and based on supplied or
  extracted listing context; TrustAI does not verify a current market price.”
- **Visual:** “Visual Inspection reports visible observations only. It cannot
  establish authenticity, ownership, or hidden condition, and it does not
  change the text score.”
- **Operations:** Runtime provider switching is deployment-time; backup/restore
  remains follow-up work under issue #88; rollback is operator-driven.
- **Deferred product scope:** Password reset/email verification/MFA, history
  search/export, automated marketplace-image retrieval, FX integration, load
  testing, and browser automation are future work rather than hidden features.

Close naturally:

> “TrustAI combines a usable buyer journey with strict application-owned
> boundaries around generated output. We delivered and deployed the product,
> tested both normal and failure paths, and kept its limits visible. The result
> is practical decision support that helps a buyer slow down, ask better
> questions, and understand the evidence before committing to a deal.”

## Rehearsal plan

### Pass 1 - technical rehearsal

- Verify production HTTPS, authenticated demo session, Case A submission,
  History, Case B/C saved results, Visual availability/consent/PV1, theme, and
  the current architecture/CI pages.
- Capture only sanitized fallbacks for Case A, History, and Visual.
- Confirm no personal account data, provider body, secret, private path, or
  notification is visible.
- Rehearse the file chooser and the Visual stop-wait threshold.
- Confirm one screen controller can complete every transition.
- Record observed output differences; update talking points to actual evidence,
  not desired output.

### Pass 2 - timing rehearsal

- Run all speaker segments with the timer and planned cut signals.
- Record segment and presenter totals.
- Require a total in the 17:00-18:00 rehearsal band.
- Tighten repeated explanations before cutting a required capability.
- Test the >18:30 and <15:30 branches deliberately without making provider
  calls solely for rehearsal.

### Pass 3 - dress rehearsal

- Use the final recording platform, layout, cameras, microphones, IDs, browser,
  light mode, inputs, and handoffs.
- Complete at least one uninterrupted start-to-finish rehearsal.
- Verify all five members remain present, visible, and audible.
- Rehearse the exact ID focus confirmation.
- Confirm the recording contains the shared screen and gallery/presenter video.
- Decide whether another polish rehearsal is needed before the final take.

## Pre-recording checklist

### Team and compliance

- [x] Exact five-person roster and official name spelling confirmed for every
      presenter.
- [ ] Final Group Project Agreement received; it lists the same five members
      and contains every required signature.
- [ ] All five members are present, visible, and prepared to speak.
- [ ] Each government-issued ID is ready; name/photo focus tested; no ID image
      will be stored in the repository.
- [ ] Recording owner, screen controller, timekeeper, fallback controller,
      final QA owner, and Quantic submitter assigned.
- [ ] Every presenter has rehearsed their owned section and handoffs.

### Capture and privacy

- [ ] Recording captures screen, voice, and presenter video.
- [ ] Microphones, cameras, lighting, and readable screen zoom checked.
- [ ] Do Not Disturb on; private tabs/apps/notifications closed.
- [ ] No passwords, tokens, cookies, headers, provider dashboards, private host
      configuration, personal user data, or raw provider output can appear.
- [ ] Presentation-only synthetic input and image folder checked.

### Product and evidence

- [ ] Production URL loads over HTTPS.
- [ ] Authorized non-personal demo session is authenticated.
- [ ] Light mode selected and stable after reload.
- [ ] Case A text ready; B and C present in History; saved values rechecked.
- [ ] PV1 is the approved 640x480 synthetic `DEMO UNIT` image.
- [ ] Visual availability and fresh-consent flow work.
- [ ] Sanitized Case A, History, and Visual fallbacks ready.
- [ ] Current architecture visual and immutable CI/release evidence preloaded.
- [ ] No workflow, deployment, provider dashboard, backup, or admin mutation is
      planned during the recording.
- [ ] Timer and cut-first signals ready.

## During-recording controls

- [ ] Recording indicator is visible to the recording owner.
- [ ] All five presenters remain present and visible.
- [ ] ID name/photo legibility is confirmed before leaving the opening.
- [ ] Screen controller performs at most one Case A submission and one Visual
      submission; no repeated clicks.
- [ ] Speakers describe only what is actually visible or cited as saved/test
      evidence.
- [ ] Timekeeper signals at 7:40, 12:20, 16:35, and 18:30.
- [ ] First cuts are theme/mobile and optional Case C.
- [ ] No presenter reads credentials, private paths, personal fields, or raw
      provider content aloud.
- [ ] Visible failure is acknowledged and routed to its honest fallback.

## Post-recording QA

Watch the entire exported file from start to finish. Do not approve it from a
spot check.

- [ ] Duration is at least 15:00 and no more than 20:00.
- [ ] There is exactly one final video file.
- [ ] All final members are present, speak meaningfully, and are visible.
- [ ] Every required government ID shows a legible name and photo.
- [ ] Screen content is readable and audio is clear throughout.
- [ ] The deployed system, functional breadth, and range of inputs are shown.
- [ ] Case A/B/C/D and LIVE/SAVED/FALLBACK states are described accurately.
- [ ] No unsupported claim, long dead time, or unacknowledged failure remains.
- [ ] No secret, personal data, ID detail beyond required name/photo, private
      operational information, or raw provider content is exposed.
- [ ] The file plays fully after export; MP4 is preferred (MOV accepted).
- [ ] Final file is uploaded to Google Drive.
- [ ] Drive access is **Anyone with the link can view**.
- [ ] The Drive link works in a logged-out/private browser and permits the full
      video to play.
- [ ] The designated submitter has the final repository, deployed app, Trello,
      design/testing report, recording, and agreement links/artifacts.

Re-record for a critical Handbook failure: missing member, missing substantive
speech, missing/illegible ID, duration outside 15-20 minutes, unusable audio or
screen, absent deployed-system demonstration, exposed secret/personal data, or
a video/access failure that cannot be corrected without changing the file.

## Score-5 coverage matrix

| Score-5 criterion | Planned timestamp / section | Evidence shown | Ready state |
|---|---|---|---|
| Thorough, clear, concise implemented-story demonstration | 1:15-10:45 | Problem, auth/form, Case A, B/C contrast, History/recovery, Visual, responsive/theme | **READY WITH FALLBACKS** |
| Range of inputs | 3:25-10:20 | Benign A, suspicious B, recent-product C, Visual PV1; contradiction D only if needed | **READY**; confirm saved B/C state |
| Correct operation throughout | Whole recording | Live preflight, single-attempt controls, authentic saved evidence, honest fallback matrix | **READY WITH CONFIRMATION** after dress rehearsal |
| Professional, legible screen share | Whole recording | Light mode, single controller, rehearsed zoom/transitions, privacy cleanup | **READY WITH CONFIRMATION** |
| Students clearly visible and audible | 0:00-17:30 | Five-person camera/audio plan and dress-rehearsal checks | **OPEN until rehearsal/recording** |
| 15-20 minute duration | Exact 17:30 table | Segment arithmetic and cut/add strategy | **READY**; final export still OPEN |

No score-5 criterion is omitted from the plan. Human/capture-dependent criteria
cannot become PASS until the recording is reviewed.

## Handbook presentation compliance matrix

| Control | Runbook provision | Current state |
|---|---|---|
| One recorded presentation with screen capture and voiceover | One coordinated recording, one controller, one final file | **READY; recording OPEN** |
| Summarize solution | 1:15-2:15 opening | **READY** |
| Demonstrate deployed functional capabilities | 2:15-10:45 user-story matrix and deployed app | **READY WITH BOUNDED FALLBACKS** |
| Every member speaks | Presenter totals: 3:30 each | **READY; attendance OPEN** |
| Every member present and visible | Gallery/recording plan and continuous presence check | **READY; final proof OPEN** |
| Government ID name/photo legible for every presenter | 0:00-1:15 procedure and QA | **READY; final proof OPEN** |
| 15-20 minutes | Exact 17:30 plan, 17:00-18:00 rehearsal band | **READY; final export OPEN** |
| One MP4 recommended / MOV accepted | Export and QA checklist | **READY; file OPEN** |
| Google Drive anyone-link access | Post-recording upload and logged-out test | **OPEN until file exists** |
| One group submitter | Recording-role table | **CONFIRM BEFORE RECORDING** |

## Open confirmations and external closure

These are real external gaps, not documentation defects:

1. **Agreement:** the exact five-member roster and official name spellings are
   confirmed; locate the final Group Project Agreement and verify that it
   matches the roster and contains all required signatures.
2. **Attendance:** confirm all five members can attend the complete final
   recording.
3. **Operational roles:** assign recording owner, screen controller,
   timekeeper, fallback controller, QA owner, and one Quantic submitter.
4. **Demo state:** confirm saved Case B/C, sanitized fallbacks, and approved PV1
   are ready immediately before recording.
5. **Dedicated sprint demos:** no authentic complete sprint-end demonstration
   set is verified. Do not reconstruct or relabel one for the presentation.
6. **GitHub grader sharing:** independently verify the Handbook-required
   `quantic-grader` repository access before submission.
7. **Trello grader access:** the canonical board is Private; provide and verify
   the required grader access without rewriting historical board activity.
8. **Backup limitation:** production backup/restore remains open under issue
   #88. Accept it explicitly as a disclosed limitation or close it with real
   evidence; do not imply it is complete.
9. **Recording and hosting:** complete the final take, full QA, MP4/MOV export,
   Google Drive anyone-link access, and logged-out playback check.
10. **Submission:** one designated member submits the final accessible links
    and signed final agreement page through Quantic.

## Final rehearsal decision

The package is **READY WITH CONFIRMATIONS** for team rehearsal. It becomes
ready for final recording only when the Agreement/signature check, all-member
attendance, recording roles, presentation-safe demo state, and one complete
uninterrupted dress rehearsal are confirmed. It becomes presentation-complete
only after the final file passes the post-recording QA and access checks.
