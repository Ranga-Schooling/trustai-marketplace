## [1.16.3](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.16.2...v1.16.3) (2026-08-28)


### Bug Fixes

* **ui:** improve auth tab contrast ([#96](https://github.com/Ranga-Schooling/trustai-marketplace/issues/96)) ([25ca4aa](https://github.com/Ranga-Schooling/trustai-marketplace/commit/25ca4aa3a5fea88161237e6f01c946fe8ad8256a))

## [1.16.2](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.16.1...v1.16.2) (2026-08-28)


### Bug Fixes

* **deploy:** repair Docker cleanup ([#93](https://github.com/Ranga-Schooling/trustai-marketplace/issues/93)) ([cca7e74](https://github.com/Ranga-Schooling/trustai-marketplace/commit/cca7e746a2220d4ed0f10bbb8d8382b8ddc4df04))

## [1.16.1](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.16.0...v1.16.1) (2026-08-28)


### Bug Fixes

* **ai:** reject unsupported risk evidence ([#90](https://github.com/Ranga-Schooling/trustai-marketplace/issues/90)) ([4a1f37b](https://github.com/Ranga-Schooling/trustai-marketplace/commit/4a1f37b8f2691255e7e26e3d5b6aab3c0c3bc126))

## [1.16.0](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.15.5...v1.16.0) (2026-08-28)


### Features

* **admin:** admin RBAC + analytics dashboard (D-15, issue [#42](https://github.com/Ranga-Schooling/trustai-marketplace/issues/42)) ([#91](https://github.com/Ranga-Schooling/trustai-marketplace/issues/91)) ([f8cb2b0](https://github.com/Ranga-Schooling/trustai-marketplace/commit/f8cb2b011775d6bf0e753fc8290e0c4631c64d14))

## [1.15.5](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.15.4...v1.15.5) (2026-08-23)


### Bug Fixes

* automate EC2 disk cleanup on every deployment ([#84](https://github.com/Ranga-Schooling/trustai-marketplace/issues/84)) ([e1f4c05](https://github.com/Ranga-Schooling/trustai-marketplace/commit/e1f4c05acc08b05dc07f5a63bea5ad114f4be9ee))

## [1.15.4](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.15.3...v1.15.4) (2026-08-21)


### Bug Fixes

* **backup:** repair Postgres backup workflow ([#89](https://github.com/Ranga-Schooling/trustai-marketplace/issues/89)) ([7e43e18](https://github.com/Ranga-Schooling/trustai-marketplace/commit/7e43e1816178af6dedcf64d28b18b7cc297e4020))

## [1.15.3](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.15.2...v1.15.3) (2026-08-20)


### Bug Fixes

* **ai:** guard against stale model knowledge ([#87](https://github.com/Ranga-Schooling/trustai-marketplace/issues/87)) ([5cdb496](https://github.com/Ranga-Schooling/trustai-marketplace/commit/5cdb496ffac743aedea9583d2062fced4116c672))

## [1.15.2](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.15.1...v1.15.2) (2026-08-18)


### Bug Fixes

* clarify text-only analysis evidence ([#85](https://github.com/Ranga-Schooling/trustai-marketplace/issues/85)) ([6a65f40](https://github.com/Ranga-Schooling/trustai-marketplace/commit/6a65f405989ea832b9f496f29da39a935e9aff6c))

## [1.15.1](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.15.0...v1.15.1) (2026-08-17)


### Bug Fixes

* restore production analysis and session handling ([#81](https://github.com/Ranga-Schooling/trustai-marketplace/issues/81)) ([6e0f51d](https://github.com/Ranga-Schooling/trustai-marketplace/commit/6e0f51dc31cca1edc5d1633f9975b3e13d33e67e))

## [1.15.0](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.14.0...v1.15.0) (2026-08-17)


### Features

* extract price/currency/seller signals in URL listing preview ([#77](https://github.com/Ranga-Schooling/trustai-marketplace/issues/77)) ([b907654](https://github.com/Ranga-Schooling/trustai-marketplace/commit/b907654c48b5eaec7afa89dc82e675cacad2b6a5)), closes [#65](https://github.com/Ranga-Schooling/trustai-marketplace/issues/65) [#21](https://github.com/Ranga-Schooling/trustai-marketplace/issues/21) [#45](https://github.com/Ranga-Schooling/trustai-marketplace/issues/45) [#62](https://github.com/Ranga-Schooling/trustai-marketplace/issues/62) [#45](https://github.com/Ranga-Schooling/trustai-marketplace/issues/45) [#21](https://github.com/Ranga-Schooling/trustai-marketplace/issues/21) [#45](https://github.com/Ranga-Schooling/trustai-marketplace/issues/45) [#21](https://github.com/Ranga-Schooling/trustai-marketplace/issues/21)

## [1.14.0](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.13.3...v1.14.0) (2026-08-17)


### Features

* scheduled Postgres backups to S3 ([#76](https://github.com/Ranga-Schooling/trustai-marketplace/issues/76)) ([7b913bd](https://github.com/Ranga-Schooling/trustai-marketplace/commit/7b913bd648cf0f7c16d812e8445009397b81e529))

## [1.13.3](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.13.2...v1.13.3) (2026-08-17)


### Bug Fixes

* self-heal startup migration for pre-Alembic create_all() bootstraps ([#73](https://github.com/Ranga-Schooling/trustai-marketplace/issues/73)) ([4703d5c](https://github.com/Ranga-Schooling/trustai-marketplace/commit/4703d5cc09915902badfbb2e1ebf43a8dd12e0e8)), closes [#69](https://github.com/Ranga-Schooling/trustai-marketplace/issues/69)

## [1.13.2](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.13.1...v1.13.2) (2026-08-17)


### Bug Fixes

* wire up History's dead onNewListing prop to an empty-state button ([#72](https://github.com/Ranga-Schooling/trustai-marketplace/issues/72)) ([9c005c5](https://github.com/Ranga-Schooling/trustai-marketplace/commit/9c005c58e065f8a28ff751be2d38a04c8cd0c424)), closes [#71](https://github.com/Ranga-Schooling/trustai-marketplace/issues/71)

## [1.13.1](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.13.0...v1.13.1) (2026-08-17)


### Bug Fixes

* wire account edit/delete UI to a real api.js client, drop dead password field ([#67](https://github.com/Ranga-Schooling/trustai-marketplace/issues/67)) ([621bc8f](https://github.com/Ranga-Schooling/trustai-marketplace/commit/621bc8f684642223e9faddd3e64d6211152cfbec)), closes [#52](https://github.com/Ranga-Schooling/trustai-marketplace/issues/52) [#54](https://github.com/Ranga-Schooling/trustai-marketplace/issues/54) [#55](https://github.com/Ranga-Schooling/trustai-marketplace/issues/55) [#56](https://github.com/Ranga-Schooling/trustai-marketplace/issues/56) [#66](https://github.com/Ranga-Schooling/trustai-marketplace/issues/66)

## [1.13.0](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.12.1...v1.13.0) (2026-08-17)


### Features

* enable HTTPS with Caddy ([#63](https://github.com/Ranga-Schooling/trustai-marketplace/issues/63)) ([7939dd4](https://github.com/Ranga-Schooling/trustai-marketplace/commit/7939dd47e58184f383f086ad4077a12f7c6f7c5e))

## [1.12.1](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.12.0...v1.12.1) (2026-08-17)


### Bug Fixes

* remove duplicate content block in AuthForm breaking landing layout ([#64](https://github.com/Ranga-Schooling/trustai-marketplace/issues/64)) ([c453e43](https://github.com/Ranga-Schooling/trustai-marketplace/commit/c453e430be439db1834fbd1fdccb5dcb9adf9333)), closes [#52](https://github.com/Ranga-Schooling/trustai-marketplace/issues/52) [#54](https://github.com/Ranga-Schooling/trustai-marketplace/issues/54) [#55](https://github.com/Ranga-Schooling/trustai-marketplace/issues/55) [#56](https://github.com/Ranga-Schooling/trustai-marketplace/issues/56) [#60](https://github.com/Ranga-Schooling/trustai-marketplace/issues/60)

## [1.12.0](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.11.0...v1.12.0) (2026-08-17)


### Features

* multi-LLM provider abstraction -- GPT and Gemini (Card [#20](https://github.com/Ranga-Schooling/trustai-marketplace/issues/20)) ([#46](https://github.com/Ranga-Schooling/trustai-marketplace/issues/46)) ([9fcf69e](https://github.com/Ranga-Schooling/trustai-marketplace/commit/9fcf69ed1ee1d8e44420161a25fdcbec0b66dd1a))

## [1.11.0](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.10.0...v1.11.0) (2026-08-17)


### Features

* categorical price plausibility (plausible/suspicious/too_good_t… ([#41](https://github.com/Ranga-Schooling/trustai-marketplace/issues/41)) ([4edc85c](https://github.com/Ranga-Schooling/trustai-marketplace/commit/4edc85c0594e4e62c2514d67aa2243e4e84aa950)), closes [#28](https://github.com/Ranga-Schooling/trustai-marketplace/issues/28)

## [1.10.0](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.9.0...v1.10.0) (2026-08-17)


### Features

* fetch listing URL content to suggest submission fields (US-2.3) ([#21](https://github.com/Ranga-Schooling/trustai-marketplace/issues/21)) ([cc6803e](https://github.com/Ranga-Schooling/trustai-marketplace/commit/cc6803ea521cd45b95c731085f6d5a82d44f4197))

## [1.9.0](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.8.1...v1.9.0) (2026-08-16)


### Features

* add DELETE /api/auth/me for account deletion (US-1.5) ([#58](https://github.com/Ranga-Schooling/trustai-marketplace/issues/58)) ([ed4dc9f](https://github.com/Ranga-Schooling/trustai-marketplace/commit/ed4dc9f7dd9876d6fa27025d66964426e8cd90f9)), closes [#52](https://github.com/Ranga-Schooling/trustai-marketplace/issues/52) [#52](https://github.com/Ranga-Schooling/trustai-marketplace/issues/52)

## [1.8.1](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.8.0...v1.8.1) (2026-08-16)


### Bug Fixes

* address PR review comments for account management and risk gauge ([#60](https://github.com/Ranga-Schooling/trustai-marketplace/issues/60)) ([cc8e9cc](https://github.com/Ranga-Schooling/trustai-marketplace/commit/cc8e9cc88086dbc6d808e58591c6c0c158d9f618)), closes [#52](https://github.com/Ranga-Schooling/trustai-marketplace/issues/52) [#54](https://github.com/Ranga-Schooling/trustai-marketplace/issues/54) [#55](https://github.com/Ranga-Schooling/trustai-marketplace/issues/55) [#56](https://github.com/Ranga-Schooling/trustai-marketplace/issues/56)

## [1.8.0](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.7.2...v1.8.0) (2026-08-10)


### Features

* implement US-4.1 -- view analysis history (list + detail) ([#48](https://github.com/Ranga-Schooling/trustai-marketplace/issues/48)) ([dd71b05](https://github.com/Ranga-Schooling/trustai-marketplace/commit/dd71b05acb6cffdfa94b7398f9e2f54fd5af4b05))

## [1.7.2](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.7.1...v1.7.2) (2026-08-10)


### Bug Fixes

* history card contrast — style .history-card as a card, not a CTA button ([#49](https://github.com/Ranga-Schooling/trustai-marketplace/issues/49)) ([0a6101b](https://github.com/Ranga-Schooling/trustai-marketplace/commit/0a6101bb50ffbf0cae00ca5ae03bd83bd2f9add5))

## [1.7.1](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.7.0...v1.7.1) (2026-08-09)


### Bug Fixes

* run Alembic migrations on container start; tolerate unknown .env keys ([#47](https://github.com/Ranga-Schooling/trustai-marketplace/issues/47)) ([d4baae7](https://github.com/Ranga-Schooling/trustai-marketplace/commit/d4baae71494bc08ee24ae2fdff119f9fec6deb96))

## [1.7.0](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.6.1...v1.7.0) (2026-08-08)


### Features

* deterministic 0-100 risk score, resolving Card [#27](https://github.com/Ranga-Schooling/trustai-marketplace/issues/27) without reopening D-05 ([#43](https://github.com/Ranga-Schooling/trustai-marketplace/issues/43)) ([164b915](https://github.com/Ranga-Schooling/trustai-marketplace/commit/164b915e26544535a37f3408f8b58f9f4a0ef008)), closes [#31](https://github.com/Ranga-Schooling/trustai-marketplace/issues/31) [#32](https://github.com/Ranga-Schooling/trustai-marketplace/issues/32)

## [1.6.1](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.6.0...v1.6.1) (2026-08-08)


### Bug Fixes

* un-skip test_low_risk_listing_gets_buy (US-3.1) ([#36](https://github.com/Ranga-Schooling/trustai-marketplace/issues/36)) ([319b351](https://github.com/Ranga-Schooling/trustai-marketplace/commit/319b351405b0abe741f405a293e9b14173acb68e))

## [1.6.0](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.5.0...v1.6.0) (2026-08-06)


### Features

* **app:** merge promo and intro into one landing column; wire up his… ([#29](https://github.com/Ranga-Schooling/trustai-marketplace/issues/29)) ([9ebe90a](https://github.com/Ranga-Schooling/trustai-marketplace/commit/9ebe90a410423f26186b2798c1889e1a69f85e00))

## [1.5.0](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.4.0...v1.5.0) (2026-08-06)


### Features

* align sign in/register screen with approved wireframes (US-1.1/… ([#25](https://github.com/Ranga-Schooling/trustai-marketplace/issues/25)) ([707f2e4](https://github.com/Ranga-Schooling/trustai-marketplace/commit/707f2e4778de8b3b9c798f2d210b72d41b65ef1e)), closes [#20](https://github.com/Ranga-Schooling/trustai-marketplace/issues/20) [#20](https://github.com/Ranga-Schooling/trustai-marketplace/issues/20) [#20](https://github.com/Ranga-Schooling/trustai-marketplace/issues/20)

## [1.4.0](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.3.0...v1.4.0) (2026-08-06)


### Features

* view and edit account profile (US-1.4) ([#24](https://github.com/Ranga-Schooling/trustai-marketplace/issues/24)) ([5c3c918](https://github.com/Ranga-Schooling/trustai-marketplace/commit/5c3c918e837646b55156f4d51a9b40df4ee9fa19))

## [1.3.0](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.2.1...v1.3.0) (2026-08-02)


### Features

* build sign-in/register form for auth flow ([#20](https://github.com/Ranga-Schooling/trustai-marketplace/issues/20)) ([0431c1b](https://github.com/Ranga-Schooling/trustai-marketplace/commit/0431c1bfca62214390499132b778b0bba5640ec7))

## [1.2.1](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.2.0...v1.2.1) (2026-08-01)


### Bug Fixes

* **docker:** bind Vite to 0.0.0.0 and wait for db healthcheck before api starts ([#33](https://github.com/Ranga-Schooling/trustai-marketplace/issues/33)) ([e0a77c2](https://github.com/Ranga-Schooling/trustai-marketplace/commit/e0a77c2fc3283eb72d1e03aec1f701c3a708bf0e))

## [1.2.0](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.1.0...v1.2.0) (2026-07-31)


### Features

* implement E3 AI analysis and risk scoring ([#12](https://github.com/Ranga-Schooling/trustai-marketplace/issues/12)) ([32bdd6e](https://github.com/Ranga-Schooling/trustai-marketplace/commit/32bdd6e8ca66ab593e835667441ec365271a0fb5)), closes [#8](https://github.com/Ranga-Schooling/trustai-marketplace/issues/8) [#8](https://github.com/Ranga-Schooling/trustai-marketplace/issues/8)

## [1.1.0](https://github.com/Ranga-Schooling/trustai-marketplace/compare/v1.0.0...v1.1.0) (2026-07-30)


### Features

* Wireframes and skeleton frontend UI ([#23](https://github.com/Ranga-Schooling/trustai-marketplace/issues/23)) ([24b0f51](https://github.com/Ranga-Schooling/trustai-marketplace/commit/24b0f5128d03cab37c481589ef9f35b2e2d59e59))

## 1.0.0 (2026-07-27)


### Features

* add API skeleton with story-mapped stubs per bounded context ([58196c9](https://github.com/Ranga-Schooling/trustai-marketplace/commit/58196c91aa6cfc886c25490f1a995d398c8946db))
* add Pydantic shared kernel and app configuration ([c804dd8](https://github.com/Ranga-Schooling/trustai-marketplace/commit/c804dd83776c78952e3a06744d68af7ec427ee0f))
* add Vite/React scaffold with stubbed components and API client ([d6d8974](https://github.com/Ranga-Schooling/trustai-marketplace/commit/d6d897414612180a7d638de3458a12d8ae2f9481))
* build sign-in/register form for auth flow ([#7](https://github.com/Ranga-Schooling/trustai-marketplace/issues/7)) ([7f1df6d](https://github.com/Ranga-Schooling/trustai-marketplace/commit/7f1df6d06d5751ab9242a413ef1c8488adf28880))
* draft listings/analyses schema, add Alembic migrations ([#8](https://github.com/Ranga-Schooling/trustai-marketplace/issues/8)) ([e188a0c](https://github.com/Ranga-Schooling/trustai-marketplace/commit/e188a0c11588cd103dd46ed6c640e17a98c8ec89))
* implement user registration, login, and auth dependency ([#6](https://github.com/Ranga-Schooling/trustai-marketplace/issues/6)) ([e67ed8d](https://github.com/Ranga-Schooling/trustai-marketplace/commit/e67ed8d41ecbf56037bb249846a7c3f68aacb2b5))
* run frontend in docker compose and wire it to the api ([#11](https://github.com/Ranga-Schooling/trustai-marketplace/issues/11)) ([ce8cc8e](https://github.com/Ranga-Schooling/trustai-marketplace/commit/ce8cc8e7cc0d344b14b34738c68734457a39c85f))


### Bug Fixes

* add psycopg2-binary driver so api container can connect to postgres ([#10](https://github.com/Ranga-Schooling/trustai-marketplace/issues/10)) ([599809c](https://github.com/Ranga-Schooling/trustai-marketplace/commit/599809c5f927d0d2765571ec9868236fee062ed7))
* **ci:** add missing conventional-changelog-conventionalcommits dependency ([#15](https://github.com/Ranga-Schooling/trustai-marketplace/issues/15)) ([d1465bf](https://github.com/Ranga-Schooling/trustai-marketplace/commit/d1465bfe6527113af5b6b38454d81c18adfdd4a9))
* **ci:** fully automate release workflow for protected main ([#16](https://github.com/Ranga-Schooling/trustai-marketplace/issues/16)) ([d2fbc3d](https://github.com/Ranga-Schooling/trustai-marketplace/commit/d2fbc3dc1e5e6190eebdafa85d1ca22b2f4d5079))
* **ci:** pin github-app-token to v2 and correct installation input ([#17](https://github.com/Ranga-Schooling/trustai-marketplace/issues/17)) ([8d170bc](https://github.com/Ranga-Schooling/trustai-marketplace/commit/8d170bc5e3d7aa5ff41b4597c91b3d3a0eeb416e))
* **ci:** resolve GitHub App installation by repository instead of ID ([#18](https://github.com/Ranga-Schooling/trustai-marketplace/issues/18)) ([9872e15](https://github.com/Ranga-Schooling/trustai-marketplace/commit/9872e1521ea8de3e783e32f03e6e5e51912f34c2))
