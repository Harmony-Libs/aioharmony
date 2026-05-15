---
name: pr-workflow
description: Create pull requests for Harmony-Libs/aioharmony. Use when creating PRs, submitting changes, or preparing contributions.
allowed-tools: Read, Bash, Glob, Grep
---

# aioharmony PR Workflow

When creating a pull request for `Harmony-Libs/aioharmony`,
follow these steps. Repo-wide conventions live in
[CLAUDE.md](../../../CLAUDE.md); this skill summarises the parts
that matter at PR-creation time.

## 1. Create branch from origin/main

`origin` points at `Harmony-Libs/aioharmony`; there is no fork in
this workflow. Always re-fetch first so the branch is based on
the latest `main`:

```bash
git fetch origin
git checkout -b <branch-name> origin/main
```

## 2. Conventional Commits — required for commits AND PR title

Every commit subject MUST follow
[Conventional Commits](https://www.conventionalcommits.org/).
The `commitlint` job in `.github/workflows/ci.yml` runs
`@commitlint/config-conventional` over every commit on the
branch, and the `commitizen` pre-commit hook does the same on
`commit-msg` locally.

**There is no separate PR-title linter** — unlike sibling repos,
this one doesn't ship a `pr-title.yml` workflow. But GitHub uses
the PR title as the squash-merge subject and
`python-semantic-release` reads the resulting commit log on
`main` to bump the version, so a malformed title silently
produces a malformed release commit. Get the title right at
PR-open time; nothing in CI will catch it.

Accepted types: `build`, `chore`, `ci`, `docs`, `feat`, `fix`,
`perf`, `refactor`, `revert`, `style`, `test`. Scope is optional.
The subject (text after `type(scope):`) must start lowercase.

Examples from recent history that passed:

```
fix: stop reconnect retry loop on concurrent disconnect
fix: support slixmpp 1.10+ connect API
feat!: drop Python 3.9 support
chore(deps): bump aiohttp from 3.11.11 to 3.13.4
```

### Pick the type that matches the release impact

`python-semantic-release` reads the commit log on `main` to
decide the next version and write `CHANGELOG.md`:

| Type                                            | Release effect                                  |
| ----------------------------------------------- | ----------------------------------------------- |
| `feat:`                                         | minor bump, shows in changelog under Features   |
| `fix:`, `perf:`                                 | patch bump, shows under Bug Fixes / Performance |
| any with `!` or `BREAKING CHANGE:` footer       | major bump                                      |
| `chore:`, `ci:`, `refactor:`, `style:`, `test:` | no bump, excluded from changelog                |
| `docs:`, `build(non-deps):`                     | no bump, excluded from changelog                |
| `build(deps):`                                  | no bump, but KEPT in changelog                  |

(`exclude_commit_patterns` in `pyproject.toml` is the source of
truth — `build(deps): ...` matches the exception that keeps
dependency bumps visible.)

A user-visible bugfix tagged `chore:` will be silently omitted
from the changelog; an internal refactor tagged `feat!:` will
mint a fake major release. Pick the type a changelog reader
would expect.

## 3. There is no PR template

The repo does not ship a `.github/PULL_REQUEST_TEMPLATE.md`, so
the PR body is freeform. Write a short description of:

- **What** the change does (one or two sentences of prose).
- **Why** — the motivating bug, firmware quirk, or feature ask.
- **Linked issues** — `fixes #N` / `closes #N` for issue
  closure, or a bare reference if related but not closing.

Keep it focused; the commit messages carry the per-commit detail.

## 4. Commit hygiene

- **Imperative-mood subject line** — "Add X", not "Added X".
- **No `Co-Authored-By` trailers for LLM tools.** Recent history
  has zero of these; the harness will try to add one by default,
  strip it before committing. Commits attribute the human who
  reviewed the change.
- Let pre-commit run (ruff lint + format, pyupgrade,
  pyproject-fmt, uv-lock, prettier, codespell, trailing-
  whitespace, etc.). If a hook auto-fixes a file, the commit
  aborts — re-stage the auto-fixed files and re-commit. **Do
  not** bypass with `--no-verify`; the `uv-lock` hook in
  particular regenerates state CI also expects.
- Write tests for behavioural changes under `tests/`. Run them
  with:

  ```bash
  uv run pytest
  ```

  The matrix runs 3.10–3.14 on Linux; if your change is
  Python-version-sensitive (e.g. typing imports, asyncio API
  differences), sanity-check against the floor (3.10).

## 5. Push and create the PR

```bash
git push -u origin <branch-name>
gh pr create --repo Harmony-Libs/aioharmony --base main \
  --title "type(scope): lowercase subject under ~70 chars" \
  --body-file /tmp/pr-body.md
```

Use `--body-file` rather than `--body "..."` so that backticks,
asterisks, and other Markdown in the body are passed through
verbatim instead of being mangled by shell quoting.

Nothing in CI lints the PR title — so once it's open, eyeball it
against the Conventional Commits rules above. If it's wrong,
`gh pr edit --title "..."` (no push needed).

## 6. After the PR is open

CI runs:

- `lint` — pre-commit (ruff lint + format, pyupgrade,
  pyproject-fmt, uv-lock, prettier, codespell, trailing-
  whitespace, etc.).
- `commitlint` — per-commit Conventional Commits check across
  the branch.
- `test` matrix — Python 3.10, 3.11, 3.12, 3.13, 3.14 on
  `ubuntu-latest`. Each cell runs `uv sync && uv run pytest`
  and uploads coverage to Codecov.

A red `test` cell on a single Python version usually means a
version-specific typing or asyncio API mismatch — check the
failing cell's traceback before assuming the test is flaky. The
suite is small (~4 files) and fast, so flakes are rare.

After merge, the `release` job runs on `main`:
`python-semantic-release` reads the commit log, decides whether
to bump the version, regenerates `CHANGELOG.md`, tags, attests
the build, and publishes to PyPI. If your commit type was
non-bumping (`chore:`, `ci:`, `refactor:`, `style:`, `test:`,
`docs:`, `build(non-deps):`), the release job will run but no
new version will be cut. That's expected — not a CI failure.
