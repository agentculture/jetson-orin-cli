# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

`jetson-orin-cli` is an **AgentCulture mesh agent** packaged as an agent-first
Python CLI. Its stated domain is operating NVIDIA Jetson Orin edge-AI devices
(Orin Nano/NX/AGX) — provisioning, inference, on-device ops.

**Important: that domain is aspirational, not yet built.** The code today is the
unmodified *culture-agent-template* baseline (cited from
[teken](https://github.com/agentculture/teken)'s `python-cli` reference): a set
of generic agent-introspection verbs (`whoami`, `learn`, `explain`, `overview`,
`doctor`, `cli`). There is **no Jetson-specific logic anywhere yet**. Adding the
provisioning/inference/ops surface is the actual work — do it by adding new noun
groups under `jetson_orin/cli/_commands/` (see "Adding a verb or noun group").

The runtime package has **zero third-party dependencies** by design (note
`dependencies = []` in `pyproject.toml`). Keep it that way: `whoami` even parses
`culture.yaml` with a hand-rolled line scanner rather than pulling in a YAML lib.
Third-party packages belong in the `dev` dependency group only.

## Three names for one thing — do not confuse them

| Form | Value | Where it's used |
|------|-------|-----------------|
| Python package / import | `jetson_orin` (underscore) | `import jetson_orin`, `--cov=jetson_orin` |
| Distribution / PyPI / mesh nick | `jetson-orin-cli` (hyphen) | `pip install`, SonarCloud key, `culture.yaml` `suffix`, `whoami` nick |
| **Console command** | **`orin`** | what you type; argparse `prog`, all `--help` / `learn` / `explain` text |

The package **`jetson-orin-cli`** installs a single console command named
**`orin`** (`[project.scripts]`: `orin = "jetson_orin.cli:main"`). Run it as
`uv run orin <verb>` or `python -m jetson_orin <verb>`. The command surface
(prog, help, `learn`, `explain`, the catalog headings, tests) all say `orin`.
The mesh-agent *identity* — `culture.yaml`'s `suffix`, the `whoami` nick, and the
`learn --json` `tool` field — stays `jetson-orin-cli`: that's the agent's name,
not its command. `explain jetson-orin-cli` still resolves (kept as a legacy
alias of `explain orin`).

## Commands

```bash
uv sync                                   # create .venv, install runtime + dev deps
uv run pytest -n auto -q                  # full suite (xdist-parallel)
uv run pytest tests/test_cli.py::test_whoami_json   # a single test
uv run pytest -n auto --cov=jetson_orin --cov-report=term   # with coverage (fail_under=60)

uv run orin whoami                        # run a verb (command is `orin`)
python -m jetson_orin whoami              # module form, equivalent

# Lint (exactly what the `lint` CI job runs — line length is 100 everywhere)
uv run black --check jetson_orin tests
uv run isort --check-only jetson_orin tests
uv run flake8 jetson_orin tests
uv run bandit -c pyproject.toml -r jetson_orin
markdownlint-cli2 "**/*.md" "#node_modules" "#.local" "#.claude/skills" "#.teken"

uv run teken cli doctor . --strict        # the agent-first rubric gate CI enforces
```

## Architecture

The CLI is a thin argparse tree with three cross-cutting contracts that the
agent-first rubric (`teken cli doctor --strict`) enforces. Understanding these
three is the key to the codebase — everything else follows from them.

**1. Structured error propagation (`cli/_errors.py` + `cli/__init__.py`).**
Every handler raises `CliError(code, message, remediation)` on failure — never
prints an error itself, never lets an exception escape. `_dispatch()` catches
`CliError`, routes it through `emit_error`, and returns `err.code`; it also wraps
*any* other exception into a `CliError` so **no Python traceback ever reaches
stderr**. Argparse's own errors (unknown verb, bad flag) are captured too:
`_CliArgumentParser` overrides `.error()` to emit the same structured shape and
exit 1 instead of argparse's default exit 2. Subparsers are built with
`parser_class=_CliArgumentParser` so this propagates to every level (including
nested noun verbs like `cli overview`).

**2. Strict stream split (`cli/_output.py`).** Results → stdout, errors and
diagnostics → stderr, **never mixed**, in both text and JSON mode. Text errors
render as two lines: `error: <message>` then `hint: <remediation>` — the `hint:`
prefix is load-bearing (the rubric greps for it). Use `emit_result` /
`emit_error` / `emit_diagnostic`; don't call `print`.

**3. Dual output mode.** Every command takes `--json`. Because argparse-level
errors fire *before* `args.json` exists, `main()` pre-scans raw argv for `--json`
and stashes the result in the class-level `_CliArgumentParser._json_hint` so even
parse failures honour the requested format. Exit-code policy lives in one place
(`_errors.py`): `0` success, `1` user error, `2` environment error, `3+`
reserved.

**Command layout.** `jetson_orin/cli/_commands/` holds one module per verb. Each
exposes a `register(sub)` that adds its subparser and a `cmd_*(args)` handler.
`cli/__init__._build_parser()` calls each module's `register()`. The `cli`
module is a **noun group** (it has a sub-subparser) and exists only to satisfy
the rubric rule that *any noun with action-verbs must expose `overview`* — it
has no action verbs yet, but models the pattern your Jetson noun groups will
follow. `overview` and `cli overview` share render helpers in `overview.py`
(`agent_sections` describes the agent; `cli_sections` describes the CLI surface).

**Explain catalog (`jetson_orin/explain/`).** `explain <path>...` resolves a
command-path tuple to verbatim markdown via `catalog.ENTRIES`. `resolve()` raises
`CliError` on an unknown path. The test `test_every_catalog_path_resolves`
iterates `known_paths()` and asserts each resolves — so **every catalog entry
must be reachable, and every verb should have an entry.**

**Identity (`whoami.py` + `doctor.py`).** Identity is declared in `culture.yaml`
(`suffix` → nick, `backend`, `model`) with a matching resident prompt file. This
agent runs `backend: colleague` (a Qwen model), so its prompt file is
`AGENTS.colleague.md` — **not `CLAUDE.md`** (this file is the seed/dev guide).
`doctor` mirrors `steward doctor`'s invariants: *prompt-file-present*,
*backend-consistency* (the `_PROMPT_FILE` map: claude→CLAUDE.md,
colleague→AGENTS.colleague.md, acp→AGENTS.md, gemini→GEMINI.md), and
*skills-present*. `whoami.find_culture_yaml()` walks up from `__file__` (not CWD)
so identity is always the agent's own; a wheel install with no `culture.yaml`
falls back to literal defaults and `doctor` reports a single info check.

## Adding a verb or noun group

1. Add `jetson_orin/cli/_commands/<name>.py` with a `register(sub)` and a
   `cmd_<name>(args)` handler. Handler returns `None`/`0` on success or an `int`
   exit code; on failure it **raises `CliError`** (don't print, don't return a
   nonzero silently).
2. Add `--json` support and honour it in the handler.
3. Wire it into `_build_parser()` in `cli/__init__.py`.
4. Add an `explain` catalog entry in `explain/catalog.py` for the new path (the
   `test_every_catalog_path_resolves` test will fail otherwise).
5. If it's a **noun group** with action-verbs, it must also expose an
   `overview` sub-verb (rubric rule — see how `cli.py` does it).
6. Run `uv run teken cli doctor . --strict` and the test suite before opening a PR.

## CI / PR workflow (every PR bumps the version)

CI lives in `.github/workflows/`:

- **tests.yml** — three jobs: `test` (pytest + coverage → optional SonarCloud
  scan, gated on `SONAR_TOKEN` so forks/token-less repos skip it), `lint` (black,
  isort, flake8, bandit, markdownlint, **and the `teken cli doctor --strict`
  rubric gate**), and `version-check`.
- **version-check** blocks merge if `pyproject.toml`'s `version` equals the
  version on `main`. **Every PR must bump the version — even docs/config/CI-only
  changes.** Use the `/version-bump patch|minor|major` skill: it updates
  `pyproject.toml` and prepends a Keep-a-Changelog entry to `CHANGELOG.md`.
- **publish.yml** — fires only on changes to `pyproject.toml` or `jetson_orin/**`.
  PRs publish a `.devN` build to TestPyPI; pushes to `main` publish to PyPI via
  OIDC Trusted Publishing (no stored token).

The `cicd` skill is the PR lane (create PR, address review threads, poll Sonar
status). `sonarclaude` queries the quality gate. Both target the SonarCloud key
`agentculture_jetson-orin-cli`.

## Vendored skills (`.claude/skills/`)

14 skills are vendored **cite-don't-import** from `guildmaster` (plus three from
`devague` and `ask-colleague` from `colleague`). `docs/skill-sources.md` is the
authoritative provenance ledger and re-sync procedure — read it before editing
anything under `.claude/skills/`. Script bodies are kept byte-verbatim; only
consumer-identifying prose and a load-bearing `type: command` frontmatter field
are adapted. To re-sync, follow the per-skill procedure in that doc rather than
hand-editing.

## Renaming the template for a new agent

The name appears across three forms — the import package `jetson_orin`, the
dist/nick `jetson-orin-cli`, and the console command `orin`. Discover every
occurrence first:

```bash
git grep -lI -e 'jetson_orin' -e 'jetson-orin'   # package + dist/nick
git grep -nwI orin                                # the console command surface
```

Then rename the package directory, the `[project] name` and `[project.scripts]`
entry in `pyproject.toml`, the `prog=`/literal strings throughout `jetson_orin/`,
`tests/`, `sonar-project.properties`, and `README.md`; update `culture.yaml`
(`suffix`/`backend`/`model`) and the resident prompt file; then rewrite this
`CLAUDE.md`.
