# TrustAI Marketplace — Submission Closeout

## Final project status

This closeout records the final state of TrustAI Marketplace at submission and
the documentation updates that followed. Earlier meeting records and the
September 4 production-validation report remain preserved as historical project
evidence.

## Final application and access

| Item | Final state | Notes |
|---|---|---|
| Application release used for submission | [`v1.21.0`](https://github.com/Ranga-Schooling/trustai-marketplace/releases/tag/v1.21.0) at `9eb7253e47cd54dd7a3084ce47c0df1747d16948` | Immutable GitHub release; includes D-22 hardening after the `v1.20.0` validation baseline |
| Deployed application | [https://trustai.mandalawi.ca](https://trustai.mandalawi.ca) | Public HTTPS and application health were rechecked before closeout |
| Repository | [Ranga-Schooling/trustai-marketplace](https://github.com/Ranga-Schooling/trustai-marketplace) | Public; the exact `quantic-grader` account has read access |
| Agile board | [TrustAI Marketplace Trello board](https://trello.com/b/wUqCGA2T/trustai-marketplace-sprint-retrospective-board) | Public final board covering delivered, deferred, superseded and cancelled work, with retrospective closeout items identified |
| Sprint demonstrations | [Sprint 1 and Sprint 2 recordings](sprints/README.md#sprint-demonstration-recordings) | Sprint 1 and Sprint 2 recordings are available. No verified recording is available for Sprint 0 or Sprint 3. |
| Backup and recovery | **OPEN** | Production backup and restore readiness remains open under [issue #88](https://github.com/Ranga-Schooling/trustai-marketplace/issues/88). |

The detailed September 4 application-boundary evidence remains in
[Final Production Validation](FINAL_PRODUCTION_VALIDATION.md). That record is
intentionally tied to `v1.20.0`; the final `v1.21.0` application release adds
D-22 cross-origin and per-user provider-spend hardening.

## Final presentation

[Final Capstone Presentation (19:58) — Google Drive](https://drive.google.com/file/d/12FEx0J6LJ7DSQhFx62VkCf6raG5ijkon/view?usp=sharing).
For the original 4K-quality video, download the file from Google Drive; browser
playback may use a lower-resolution stream.

The final file is `TrustAI_Capstone_Presentation_FINAL_4K_v6.mp4` with a
duration of 19:58.067. The final presentation includes a working-product
demonstration alongside product, architecture, testing, and deployment content.

## Agreement and submission

The signed Group Project Agreement was submitted privately through Quantic and
is not included in the public repository.

The team completed the project and presentation submissions through Quantic on
September 13 at approximately 14:25 PDT.

## Post-submission repository chronology

Documentation-only PRs [#116](https://github.com/Ranga-Schooling/trustai-marketplace/pull/116)
and [#117](https://github.com/Ranga-Schooling/trustai-marketplace/pull/117)
merged after the September 13 submission. Current `main` may therefore be newer
than the `v1.21.0` application release without representing a newer application
build. These documentation updates postdate the submitted `v1.21.0` application
release and do not represent changes to application behavior.
