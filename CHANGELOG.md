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
