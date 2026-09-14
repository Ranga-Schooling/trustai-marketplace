# AI Disclosure

## AI Strategy

AI tools were used during the TrustAI Marketplace project as engineering,
review and editorial assistants. They helped examine implementation choices,
surface failure cases, draft test ideas, reconcile documentation with evidence
and refine presentation material. They were not treated as authoritative.
Source code, tests, primary sources, Git history, observed application behaviour
and human decisions remained controlling. The project team retains responsibility
for, and must be able to explain, the submitted work.

## Scope and AI Citations

| Scope | Tool / model | Action | Evaluation | Protocol | Reference |
|---|---|---|---|---|---|
| Software engineering, architecture and testing | OpenAI Codex Desktop (`gpt-5.6-sol` in the available project record) | Assisted with repository analysis, implementation and debugging proposals, test design and adversarial review. | Useful for tracing interactions and edge cases, but sometimes incomplete or over-broad; accepted changes were checked against code, tests, diffs, CI and pull-request controls. | Treat suggestions as proposals, preserve contracts and require source inspection and applicable tests before acceptance. | Private development record; available directly to Quantic if required. |
| Research, documentation and presentation | OpenAI Codex Desktop (`gpt-5.6-sol` in the available project record) | Supported source discovery, factual reconciliation, editing, rubric checks, presentation planning and visual review. | Helped organize evidence, but claims still required confirmation from primary sources, repository evidence or observed results. | Keep primary evidence authoritative, label unknowns and exclude secrets, personal data and private operations. | Private development record; available directly to Quantic if required. |
| Automated pull-request review | GitHub Copilot pull-request reviewer (underlying model not exposed in the review record) | Supplied advisory comments on Visual Inspection pull request [#99](https://github.com/Ranga-Schooling/trustai-marketplace/pull/99). | Contributors assessed the comments; human review and required checks remained the merge gates. | Treat bot feedback as non-authoritative and validate resulting changes through the normal pull-request process. | [PR #99](https://github.com/Ranga-Schooling/trustai-marketplace/pull/99) |

## Product-model boundary

The models used by TrustAI itself are distinct from development assistance.
When production configuration selects the OpenAI text adapter, the released
source uses GPT-5.6 Terra through the Responses API. Its independently configured
OpenAI Visual Inspection path is identified with `gpt-4o-mini`. The code also
contains deterministic mock, Groq and Gemini adapters. Separate
research in [PR #103](https://github.com/Ranga-Schooling/trustai-marketplace/pull/103)
considered OpenAI Terra and Sol, Gemini 3.7 Flash and a Groq split architecture;
it recorded no formal winner and was not merged wholesale. Earlier planning
references to Groq do not describe the final production selection.

GitHub Actions, gitStream, semantic-release and the TrustAI release bot provided
CI, policy and release automation. They are not represented here as generative
AI authoring tools.

Development records containing private project context are retained separately
and can be provided to Quantic through an appropriate private channel if requested.
