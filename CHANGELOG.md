# CHANGELOG


## v0.4.0 (2025-01-24)

### Features

- Use orjson if its installed ([#62](https://github.com/Harmony-Libs/aioharmony/pull/62),
  [`cbb8a14`](https://github.com/Harmony-Libs/aioharmony/commit/cbb8a146916daca53498c102942223ca72179082))


## v0.3.0 (2025-01-24)

### Features

- Use eager start to callback task on Python 3.12+
  ([#60](https://github.com/Harmony-Libs/aioharmony/pull/60),
  [`ab912d5`](https://github.com/Harmony-Libs/aioharmony/commit/ab912d5d477f3a0488fb0d1bdbb3228d96f60bc7))


## v0.2.14 (2025-01-24)

### Bug Fixes

- Prefer WebSockets over XMPP ([#58](https://github.com/Harmony-Libs/aioharmony/pull/58),
  [`381ec77`](https://github.com/Harmony-Libs/aioharmony/commit/381ec7759c9985d80698b19d99303549a601684a))


## v0.2.13 (2025-01-24)

### Bug Fixes

- Ensure cancellation is not swallowed on connect failure and in response handlers
  ([#57](https://github.com/Harmony-Libs/aioharmony/pull/57),
  [`d805a4a`](https://github.com/Harmony-Libs/aioharmony/commit/d805a4a70b792c84d4ff357518dec22b287225b1))


## v0.2.12 (2025-01-24)

### Bug Fixes

- Adjust timeout calls to use async context manager to fix compat with async_timeout 5+
  ([#55](https://github.com/Harmony-Libs/aioharmony/pull/55),
  [`dc96aee`](https://github.com/Harmony-Libs/aioharmony/commit/dc96aee91061381b3f7fa94ea6c08e410cc09526))


## v0.2.11 (2025-01-24)

### Bug Fixes

- Ensure strong references are held to tasks
  ([#50](https://github.com/Harmony-Libs/aioharmony/pull/50),
  [`36f1f28`](https://github.com/Harmony-Libs/aioharmony/commit/36f1f289431ad3efc26cb9611a091b3b8fbedac5))

fixes https://github.com/home-assistant/core/issues/50492

This was actually fixed in #34

This is a dummy PR for the changelog

- Release process ([#51](https://github.com/Harmony-Libs/aioharmony/pull/51),
  [`91b13da`](https://github.com/Harmony-Libs/aioharmony/commit/91b13dadbb5f8a215ef8b8c95a691b8382920024))


## v0.2.10 (2023-03-16)


## v0.2.9 (2022-01-10)


## v0.2.8 (2021-10-17)


## v0.2.7 (2021-02-05)


## v0.2.6 (2020-07-29)


## v0.2.5 (2020-06-19)


## v0.2.4 (2020-06-08)


## v0.2.3 (2020-06-05)


## v0.2.1 (2019-09-03)


## v0.1.3 (2019-01-01)


## v0.1.2 (2018-12-30)


## v0.1.1 (2018-12-29)


## v0.1.0 (2018-12-28)
