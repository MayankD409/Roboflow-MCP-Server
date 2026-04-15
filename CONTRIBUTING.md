# Contributing

Thanks for wanting to help. This project is small enough that a little
discipline keeps it sharp, so please read this before opening a PR.

## Ground rules

- Be kind. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
- Tests first. No tool lands without tests.
- Keep changes small and focused. One tool or one concern per PR.
- Conventional Commits. `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.

## Branching (Git Flow)

| Branch | Purpose | How to update |
|---|---|---|
| `main` | Tagged, released code | PR from `release/*` or `hotfix/*` only |
| `develop` | Integration branch | PR from `feature/*` or `bugfix/*` |
| `feature/<name>` | New work | Branch from `develop` |
| `bugfix/<name>` | Non-urgent fixes | Branch from `develop` |
| `release/x.y.z` | Stabilise a release | Branch from `develop`, merges to `main` and back to `develop` |
| `hotfix/x.y.z` | Urgent fix on prod | Branch from `main`, merges to `main` and back to `develop` |

Neither `main` nor `develop` accepts direct pushes. Open a PR.

## Setup

You need Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/MayankD409/Roboflow-MCP-Server.git
cd Roboflow-MCP-Server
uv sync --all-extras
uv run pre-commit install --hook-type commit-msg --hook-type pre-commit
cp .env.example .env  # fill in your Roboflow key for local tests
```

## The loop

We write tests first, implementation second. For a new tool:

1. Open an issue using the **Tool request** template and get a thumbs-up from
   a maintainer. This avoids duplicate work.
2. Branch off `develop`: `git checkout -b feature/my-tool develop`.
3. Write a failing unit test in `tests/unit/tools/` that describes the tool's
   input, output, and one error path. Use `respx` to mock HTTP, never hit the
   real Roboflow API in unit tests.
4. Run `make test`. Red.
5. Implement the tool in `src/roboflow_mcp/tools/`. Keep it under ~80 lines.
   Use `pydantic` models for input and output.
6. Run `make test`. Green.
7. Run `make lint typecheck`. No warnings.
8. Add a row to `docs/TOOLS.md` describing the tool in plain English.
9. Add a bullet under `## [Unreleased]` in `CHANGELOG.md`.
10. Commit with a Conventional Commit message, push, open a PR to `develop`.

## Make targets

```bash
make test         # pytest with coverage
make lint         # ruff format --check + ruff check
make typecheck    # mypy
make inspector    # launch MCP Inspector against this server
make dev          # run the server locally over stdio
```

## PR checklist

The PR template has the full list, but at minimum:

- [ ] Tests cover the happy path and one failure mode.
- [ ] `make lint typecheck test` pass locally.
- [ ] `CHANGELOG.md` updated.
- [ ] `docs/TOOLS.md` updated if you touched or added a tool.
- [ ] The PR description explains *why*, not just *what*.

## Reviews

A maintainer will review within a few days. Small PRs get reviewed faster.
Don't take feedback personally; we're reviewing the code, not you.

## Releasing

Maintainer only. See the release section of `docs/TOOLS.md` once we cut `v0.1.0`.
