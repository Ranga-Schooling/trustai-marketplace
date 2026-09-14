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
| Architecture, implementation, testing and documentation | Anthropic Claude Code (public commit metadata identifies Claude Sonnet 5 and Claude Opus 5) | Assisted work recorded in merged PRs #18, #34, #111, #112, #113 and #117. | Changes were evaluated against repository evidence, tests, diffs, human review and required checks. | Treat outputs as proposals and verify affected code, tests and claims before acceptance. | Public commit and pull-request history. |
| Repository workflow, deployment and CI/CD documentation | Cursor Agent (model not established) | Co-authored commits represented in merged PRs #4, #5, #37, #38, #44, #50, #51 and #101. | Accepted changes remained subject to review, CI and repository controls. | Verify generated changes through diffs, tests and normal pull-request review. | Public commit and pull-request history. |
| Automated pull-request review and accepted fixes | GitHub Copilot pull-request reviewer and Copilot Autofix (underlying models not exposed in repository evidence) | Produced 19 reviews across PRs #4, #37, #38, #44, #50, #51, #99 and #101; three accepted Autofix commits contributed to #4 and #51. | Contributors assessed the findings and accepted changes; human review and required checks remained the merge gates. | Treat bot findings and fixes as non-authoritative and validate them through source inspection, tests and normal pull-request controls. | Public review and commit history. |

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
