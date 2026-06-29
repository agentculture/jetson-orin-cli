"""Markdown catalog for ``orin explain <path>``.

Each entry is verbatim markdown. Keys are command-path tuples. The empty tuple,
``("orin",)``, and the legacy ``("jetson-orin-cli",)`` alias all resolve to the
root entry.

Keep bodies self-contained: an agent reading one entry should get enough
context without chaining reads.
"""

from __future__ import annotations

_ROOT = """\
# orin

`orin` is the command installed by the **jetson-orin-cli** package — an
agent-first CLI (cited from the teken `python-cli` reference) for an AgentCulture
mesh agent. It carries a mesh identity (`culture.yaml` + the resident prompt
file), the canonical guildmaster skill kit under `.claude/skills/`, and a
buildable/deployable package baseline.

## Verbs

- `orin whoami` — identity probe from `culture.yaml`.
- `orin learn` — structured self-teaching prompt.
- `orin explain <path>` — markdown docs for any noun/verb.
- `orin overview` — descriptive snapshot of the agent.
- `orin doctor` — check the agent-identity invariants.
- `orin cli overview` — describe the CLI surface.

## Exit-code policy

- `0` success
- `1` user-input error
- `2` environment / setup error
- `3+` reserved

## See also

- `orin explain whoami`
- `orin explain doctor`
"""

_WHOAMI = """\
# orin whoami

Reports the agent's identity from `culture.yaml`: nick (`suffix`), backend,
served model, and the package version. Read-only.

## Usage

    orin whoami
    orin whoami --json
"""

_LEARN = """\
# orin learn

Prints a structured self-teaching prompt covering purpose, command map,
exit-code policy, `--json` support, and the `explain` pointer.

## Usage

    orin learn
    orin learn --json
"""

_EXPLAIN = """\
# orin explain <path>

Prints markdown documentation for any noun/verb path. Unlike `--help` (terse,
positional), `explain` is global and addressable by path.

## Usage

    orin explain orin
    orin explain whoami
    orin explain --json <path>
"""

_OVERVIEW = """\
# orin overview

Read-only descriptive snapshot of the agent: identity (from `culture.yaml`), the
verb surface, and the sibling-pattern artifacts the template carries. Accepts an
ignored `target` so a stray path never hard-fails.

## Usage

    orin overview
    orin overview --json
"""

_DOCTOR = """\
# orin doctor

Checks the agent-identity invariants `steward doctor` verifies:
prompt-file-present and backend-consistency (`colleague` → `AGENTS.colleague.md`), plus a
skills-present check. Exits 1 when unhealthy.

## Usage

    orin doctor
    orin doctor --json
"""

_CLI = """\
# orin cli

Noun group for CLI-surface introspection. `cli overview` describes the CLI
itself (distinct from the global `overview`, which describes the agent).

## Usage

    orin cli overview
    orin cli overview --json
"""


ENTRIES: dict[tuple[str, ...], str] = {
    (): _ROOT,
    ("orin",): _ROOT,
    ("jetson-orin-cli",): _ROOT,  # legacy alias
    ("whoami",): _WHOAMI,
    ("learn",): _LEARN,
    ("explain",): _EXPLAIN,
    ("overview",): _OVERVIEW,
    ("doctor",): _DOCTOR,
    ("cli",): _CLI,
    ("cli", "overview"): _CLI,
}
