# Notes for LLM contributors

A short orientation file for an LLM working in this repo. Skim
before making changes; keep edits consistent with what's described
here. Read [README.rst](README.rst) for the user-facing intro and
[PROTOCOL.md](PROTOCOL.md) for the Harmony wire protocol notes.

## What this project is

`aioharmony` is an asyncio Python library for connecting to and
controlling [Logitech Harmony](https://www.logitech.com/en-us/harmony-universal-remotes.html)
Hub and Link devices. It's the underlying transport used by
[Home Assistant](https://www.home-assistant.io/integrations/harmony/)'s
Harmony integration. The repo lives at
[`Harmony-Libs/aioharmony`](https://github.com/Harmony-Libs/aioharmony);
its lineage is `bkanuka/pyharmony` → `iandday/pyharmony` →
`aioharmony` (with the asyncio rewrite and reconnect logic added
along the way).

Two transport backends are shipped from the same higher-level
client:

- **`WEBSOCKETS`** (`src/aioharmony/hubconnector_websocket.py`) —
  `aiohttp`-based; what modern Harmony firmware speaks on port 8088. This is the default path most callers hit.
- **`XMPP`** (`src/aioharmony/hubconnector_xmpp.py`) —
  `slixmpp`-based; legacy path for hubs that still have XMPP
  enabled on port 5222.

`HarmonyAPI` (in `harmonyapi.py`) is a thin wrapper around
`HarmonyClient` (in `harmonyclient.py`). Callers import
`HarmonyAPI`; everything below it is implementation. Don't add
behaviour to `HarmonyAPI` that isn't a pass-through to
`HarmonyClient`.

## Code style

- **Docstrings: terse, default to single-line.** A docstring is
  the function's _contract_, not its narrative. Most docstrings
  should be one line — `"""Summary."""` — describing what the
  function does. Multi-line is the exception, only justified when
  there is non-obvious caller-visible behaviour the type
  signature and parameter names don't already convey.

  **What does NOT belong in docstrings or comments:**
  - Rationale / motivation / "why we used to do X" — that's the
    PR description and commit message. Git already remembers.
  - Cross-references to issue numbers ("closes #N", "follow-up
    to #M") — the PR body and the changelog carry those.
  - Restatement of the function body in prose. If the next
    docstring line just describes the next line of code, delete
    the docstring line.
  - Test docstrings retelling the production-side story. A test
    docstring should name what the test pins, in one sentence —
    not re-explain the bug, the fix, or the surrounding flow.

- **Comments**: same bar. Default to writing no comments. Add
  one only when the _why_ is non-obvious: a hidden constraint, a
  subtle invariant, a workaround for a specific bug (e.g. a
  Harmony Hub firmware quirk), behaviour that would surprise a
  reader. If removing the comment wouldn't confuse a future
  reader, don't write it.

- **Don't remove existing comments** unless the code they
  describe is gone. Comments around the reconnect loop, the
  websocket heartbeat values, and the slixmpp connect/disconnect
  handshake exist _because_ removing them previously regressed
  reconnect behaviour on flaky links — see the `_reconnect` /
  hub_disconnect race noted in the v1.0.3 changelog entry.

- **Line length**: 88 (ruff default). `requires-python = ">=3.10"`,
  `target-version = "py310"` for ruff, `--py310-plus` for
  pyupgrade. Don't introduce 3.11+-only syntax — `match`/`case`,
  `Self`, `typing.override`, etc. are off-limits until the floor
  moves. PEP 604 unions (`X | Y`) and `list[X]` / `dict[K, V]`
  generics are fine; the codebase already uses them throughout
  `const.py`.

- **Imports**: ruff/isort sorted (`known_first_party =
["aioharmony", "tests"]`). Prefer absolute imports rooted at
  `aioharmony.*`. The codebase has a couple of relative imports
  (`from .json import ...`); leave them alone in files where
  they already exist, but don't introduce new ones.

- **Logging**: module-level `_LOGGER = logging.getLogger(__name__)`,
  use `%`-style format strings (`_LOGGER.debug("%s: ...",
ip_address)` rather than f-strings). `flake8-logging-format`
  (`G`) is enabled in ruff and will flag f-string log calls.

- **JSON**: import from `aioharmony.json`, not from `json` or
  `orjson` directly. The shim prefers `orjson` when installed
  and falls back to stdlib `json` with `separators=(",", ":")`.

- **`async-timeout` over `asyncio.timeout`.** The codebase uses
  `async_timeout.timeout` consistently because the 3.10 floor
  still includes a version where `asyncio.timeout` is brand-new;
  follow suit rather than mixing the two.

## Commit / PR conventions

- **Conventional Commits, lowercase subject.** The
  `commitlint`-CI job (`.github/workflows/ci.yml`) runs
  `@commitlint/config-conventional` over every commit on the
  branch, and the `commitizen` pre-commit hook does the same on
  `commit-msg` locally. Accepted types: `build`, `chore`, `ci`,
  `docs`, `feat`, `fix`, `perf`, `refactor`, `revert`, `style`,
  `test`. Scopes are optional. Subject (text after
  `type(scope):`) must start lowercase.

  Examples from recent history that passed:
  - `fix: stop reconnect retry loop on concurrent disconnect`
  - `fix: support slixmpp 1.10+ connect API`
  - `feat!: drop Python 3.9 support`
  - `chore(deps): bump aiohttp from 3.11.11 to 3.13.4`

- **No separate PR-title linter.** Unlike some sibling repos,
  this one does _not_ ship a `pr-title.yml` workflow — only
  per-commit `commitlint` runs. But GitHub uses the PR title as
  the squash-merge subject and `python-semantic-release` reads
  the resulting `main`-branch commit log to bump versions, so
  the PR title still has to be a valid Conventional Commit. Get
  it right at PR-open time; nothing in CI will catch a malformed
  title.

- **Releases are commit-driven.** `python-semantic-release` (see
  `[tool.semantic_release]` in `pyproject.toml` and the
  `release` job in `ci.yml`) reads the commit log on `main` to
  decide the next version, write `CHANGELOG.md`, tag, attest,
  and publish to PyPI. The mapping:

  | Type                                            | Release effect |
  | ----------------------------------------------- | -------------- |
  | `feat:`                                         | minor bump     |
  | `fix:`, `perf:`                                 | patch bump     |
  | any `!` or `BREAKING CHANGE:` footer            | major bump     |
  | `chore:`, `ci:`, `refactor:`, `style:`, `test:` | no bump        |
  | `docs:`, `build(non-deps):`                     | no bump        |

  `chore`, `ci`, `refactor`, `style`, `test`, and `build` (non-
  deps) are excluded from the changelog by
  `[tool.semantic_release.changelog].exclude_commit_patterns`.
  `build(deps): ...` _is_ kept in the changelog so dependency
  bumps stay visible.

- **No `Co-Authored-By` trailers for LLM authorship.** Recent
  commit history has zero `Co-Authored-By` lines; keep it that
  way. Commits attribute the human who reviewed the change, not
  the tool that produced the draft. (The harness will try to
  add one by default — strip it from the message before
  committing.)

- **No PR template.** The repo doesn't ship a
  `.github/PULL_REQUEST_TEMPLATE.md`, so the body is freeform —
  describe what the change does and why, link the issue if one
  exists. The `pr-workflow` skill under `.claude/skills/`
  summarises this end-to-end.

- **Pre-commit auto-fixes; re-stage.** `ruff --fix`,
  `ruff-format`, `pyupgrade --py310-plus`, `pyproject-fmt`,
  `uv-lock`, `prettier`, `codespell`, and the
  `pre-commit-hooks` set (trailing-whitespace, end-of-file-fixer,
  debug-statements, etc.) run on commit and will modify files
  in place. When a hook rewrites a file, the commit aborts —
  re-stage the auto-fixed files and commit again. **Don't**
  bypass with `--no-verify`.

## Running tests

The repo uses `uv` for dependency management (see the `release`
build command and the `setup-uv` step in `ci.yml`):

```bash
uv sync
uv run pytest
```

CI runs the matrix across Python 3.10, 3.11, 3.12, 3.13, and 3.14
on `ubuntu-latest` (see `ci.yml`). There's no Windows or macOS leg
and no big-endian leg — the wire format is JSON over WebSocket /
XMPP so endianness doesn't come up.

`pytest-asyncio` is in the dev group and runs in `asyncio_mode =
"auto"` (set in `pyproject.toml`), so every `async def test_*`
is collected as an asyncio test automatically — don't add
`@pytest.mark.asyncio` decorators or module-level `pytestmark`
lines. Coverage is collected via `pytest-cov` with `branch =
true` and uploaded to Codecov from each matrix cell.

### Reconnect-test fixture

Tests that exercise `_reconnect` (in `hubconnector_websocket.py`
and `harmonyclient.py`) monkeypatch `asyncio.sleep` to skip the
backoff so the suite doesn't pay several seconds per test. The
fixture was promoted to `autouse` in PR #102 after listener
tests independently hit the same 1s backoff. If you add a new
test that touches the reconnect loop, it'll pick the fixture up
automatically; if you add a test that genuinely _needs_ real
sleep, opt out explicitly rather than removing the autouse
marker.

## Architecture / useful entry points

| Path                                       | What                                                                                                          |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| `src/aioharmony/harmonyapi.py`             | `HarmonyAPI` — thin public wrapper over `HarmonyClient`. Add only pass-throughs here.                         |
| `src/aioharmony/harmonyclient.py`          | `HarmonyClient` — core hub client; owns connect / reconnect / dispatch / callbacks.                           |
| `src/aioharmony/hubconnector_websocket.py` | `aiohttp` WebSocket transport (`WEBSOCKETS` protocol). Owns the heartbeat and reconnect loop.                 |
| `src/aioharmony/hubconnector_xmpp.py`      | `slixmpp` XMPP transport (`XMPP` protocol). Sensitive to slixmpp API changes — see v1.0.3 fix.                |
| `src/aioharmony/handler.py`                | `Handler` — wraps a Future / Event / coroutine / callable so the response router can fan out.                 |
| `src/aioharmony/responsehandler.py`        | `ResponseHandler` — pulls JSON off the queue, matches by `msgid` + regex, fires registered handlers.          |
| `src/aioharmony/helpers.py`                | `call_callback` and friends; coroutine vs. plain-callable dispatch + task bookkeeping.                        |
| `src/aioharmony/const.py`                  | `PROTOCOL` literal, `HUB_COMMANDS` table, all the `*CallbackType` / `Client*Type` NamedTuples.                |
| `src/aioharmony/exceptions.py`             | Exception hierarchy rooted at `HarmonyException`; `TimeOut` inherits both `HarmonyClient` and `TimeoutError`. |
| `src/aioharmony/json.py`                   | `json_dumps` / `json_loads` shim — prefers `orjson`, falls back to stdlib. Always import via this module.     |
| `src/aioharmony/__main__.py`               | CLI entry point — `aioharmony` console script, used for manual testing against a real hub.                    |
| `tests/test_hubconnector_websocket.py`     | Reconnect / heartbeat / close-type tests for the WebSocket backend.                                           |
| `tests/test_hubconnector_xmpp.py`          | Smaller surface — mostly the XMPP-specific connect path.                                                      |
| `PROTOCOL.md`                              | Wire-level notes on Harmony's XMPP/IQ protocol — refer here before guessing at field names.                   |
| `pyproject.toml`                           | Ruff config (extensive lint set), pytest options, semantic-release config, mypy strict settings.              |
| `.pre-commit-config.yaml`                  | All pre-commit hooks; mypy is _disabled_ here (commented out) — type-checking is opt-in only.                 |

## Things that have bitten us

These are non-obvious traps that have surfaced in this repo's
recent history (see `CHANGELOG.md`). If you're touching the
reconnect path or either connector, read this first.

- **`_reconnect` must re-read `_connected` / `_auto_reconnect`
  between attempts.** The retry loop runs `await asyncio.sleep`
  between attempts; a `hub_disconnect()` that arrives during the
  sleep won't be observed if the loop only checks the flag once
  on entry. The v1.0.3 fix re-reads both flags after each sleep —
  don't refactor that re-read back out. The flags mean "the
  caller still wants us connected", and concurrent disconnect is
  a real path (Home Assistant tears clients down on shutdown).

- **slixmpp keeps reshaping `ClientXMPP.connect()`.** 1.10 swapped
  `connect(address=, disable_starttls=, use_ssl=)` for
  `connect(host=, port=)` and moved the TLS toggles onto
  instance attributes (`enable_starttls`, `enable_direct_tls`).
  Harmony Hubs speak plain XMPP on the LAN, so both should be
  `False`. The `dependencies` pin in `pyproject.toml` is
  `slixmpp>=1.10`; lower versions will not work with the current
  `hubconnector_xmpp.py`.

- **WebSocket listener exits must call `_reconnect`.** The v1.0.2
  fix added explicit reconnect triggers for `ClientError` (the
  heartbeat-timeout path), `WSMsgType.ERROR`, and unexpected
  exceptions in the loop body, plus `WSMsgType.CLOSE` /
  `CLOSING`. The membership check uses
  `_WS_CLOSE_TYPES = frozenset({...})` at module level — leave
  the frozenset module-level so it isn't rebuilt on every
  message.

- **Heartbeat tuning is firmware-sensitive.** `_WS_HEARTBEAT =
30` (ping every 30s, pong expected within 15s) was chosen for
  real Harmony Hub firmware behaviour on flaky WiFi. Don't
  retune without empirical data — a too-aggressive heartbeat
  drops live connections, too-loose lets a dead hub linger past
  Home Assistant's poll window.

- **`PROTOCOL` is a `Literal["WEBSOCKETS", "XMPP"]`.** PR #100
  fixed a `TypeError` at import time caused by the old
  declaration. Keep it as a `Literal`; the constants
  `WEBSOCKETS = "WEBSOCKETS"` and `XMPP = "XMPP"` are the
  string values, the `PROTOCOL` alias is the type.

- **`uv.lock` is committed and updated by pre-commit / by the
  release job.** The `uv-lock` pre-commit hook regenerates it
  whenever `pyproject.toml` changes; the `release` job in
  `ci.yml` also runs `uv lock && git add uv.lock` before
  building. Don't hand-edit it — let the tooling regenerate.

## Things not to do

- **Don't introduce 3.11+-only syntax.** The package supports
  3.10+ and pyupgrade is pinned to `--py310-plus`.
- **Don't add `Co-Authored-By` trailers for LLM tools.** Project
  preference — see _Commit / PR conventions_ above. The harness
  will try to add one by default; strip it before committing.
- **Don't pick a Conventional Commit type that under- or over-
  states the release impact.** `chore:` for a user-visible
  bugfix hides it from the changelog; `feat!:` for an internal
  refactor mints a fake major release. `python-semantic-release`
  is downstream of your choice.
- **Don't import `json` or `orjson` directly** in `aioharmony/*`
  modules — go through `aioharmony.json`. Tests can use stdlib
  `json` since they don't ship in the wheel.
- **Don't use `logging` f-string format calls** — ruff's `G`
  rules will reject them. `_LOGGER.debug("%s: ...", arg)`, not
  `_LOGGER.debug(f"{arg}: ...")`.
- **Don't bypass pre-commit with `--no-verify`.** If a hook
  fails, fix the underlying issue. The `uv-lock` hook in
  particular regenerates state that CI also expects.
- **Don't add behaviour to `HarmonyAPI` that isn't a
  pass-through.** `HarmonyAPI` is the public surface; logic
  belongs in `HarmonyClient` so the CLI and the wrapper see the
  same behaviour.
