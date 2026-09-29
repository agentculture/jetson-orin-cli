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

## Machine-scope verbs (Jetson Orin host telemetry)

- `orin status` — machine-wide scope, anomalies first (the headline); includes
  the flashed L4T release.
- `orin memory` — unified RAM + swap (CPU and iGPU share one pool).
- `orin gpu` — Jetson Orin iGPU: utilization, temp, power, GPU processes.
- `orin disk` — filesystem usage for real block devices.
- `orin thermal` — SoC thermal zones and hwmon sensors.
- `orin containers` — running Docker containers and health.
- `orin network` — interfaces, default route, reachable addresses.
- `orin processes` — top processes by resident memory.

All machine-scope verbs are read-only, support `--json`, and exit 0 even when a
subsystem is absent (it reports `available: false`). `doctor` is the health gate.

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

_STATUS = """\
# orin status

Machine-wide scope of Jetson Orin, anomalies first. Calls every domain
collector once and prints a Host header (including the flashed L4T release,
e.g. `R39.2.0`, read from `/etc/nv_tegra_release`), an Attention block (merged
warnings from all subsystems), and a compact one-liner per subsystem. The
headline entry point — drill into any line with its verb (`memory`, `gpu`, …).

The L4T field degrades to `n/a` off-Jetson (the release file only exists on a
flashed Jetson board) rather than raising.

Read-only; exits 0 even if a subsystem is unavailable.

## Usage

    orin status
    orin status --json
"""

_MEMORY = """\
# orin memory

Unified memory + swap snapshot from `/proc/meminfo`. On Jetson Orin the CPU
cores and Ampere iGPU share ONE memory pool — there is no separate VRAM —
so memory pressure here is a GPU-workload signal too. Warns on low available
memory or heavy swap use.

## Usage

    orin memory
    orin memory --json
"""

_GPU = """\
# orin gpu

Jetson Orin iGPU snapshot via `nvidia-smi`, with a sysfs fallback. Because
memory is unified, `nvidia-smi` reports aggregate `memory.total/used` as
`[N/A]`; this verb instead sums the per-process compute-app memory to report
how much of the shared pool is attributed to the GPU.

On real Orin hardware `nvidia-smi` is present but *thin*: it reports
`name`/`utilization.gpu`/`utilization.memory`, but `temperature.gpu`,
`power.draw`, and `clocks.sm` come back `[N/A]` — the iGPU doesn't expose those
counters through NVML the way a discrete card does. When nvidia-smi is
unhelpful like this (or entirely absent), those fields are backfilled from
stable sysfs nodes instead: `/sys/class/devfreq` (clock), `/sys/class/thermal`
(GPU thermal zone), and the `VDD_GPU` rail under `/sys/class/hwmon` (power).
Whichever fields were backfilled are recorded in
`data["sysfs_augmented_fields"]` and reflected in `source`
(`nvidia-smi`, `nvidia-smi+sysfs`, or plain `sysfs`). Unavailable (exit 0) only
when neither nvidia-smi nor any sysfs node yields anything.

## Usage

    orin gpu
    orin gpu --json
"""

_DISK = """\
# orin disk

Filesystem usage for real (non-virtual) block devices, read via `/proc/mounts`
and `os.statvfs` — no `df` dependency. Virtual filesystems and snap `loop`
mounts are filtered out. Warns when a filesystem is >=85% full.

## Usage

    orin disk
    orin disk --json
"""

_THERMAL = """\
# orin thermal

SoC thermal zones (`/sys/class/thermal`) and hwmon sensors
(`/sys/class/hwmon`: nvme, wifi PHY, INA3221/INA238 power monitors, …) in
Celsius. No `lm-sensors` dependency. GPU die temperature comes from
`nvidia-smi`/sysfs (see `gpu`). Warns on any sensor at or above 85 C.

## Usage

    orin thermal
    orin thermal --json
"""

_CONTAINERS = """\
# orin containers

Running Docker containers via `docker ps`, with health. Images served from
`nvcr.io` are tagged GPU-likely (heuristic). Warns on any container reporting
`(unhealthy)`. Unavailable (exit 0) when docker is absent or the daemon is
down.

## Usage

    orin containers
    orin containers --json
"""

_NETWORK = """\
# orin network

Interfaces, default route, and reachable addresses, summarized from `ip -br
addr` and `ip route show default`. Named interfaces (wifi/ethernet/tailscale/
bridges) are listed with their IPv4; the many container `veth` pairs are rolled
up to a count. "Reachable" excludes docker bridge gateways and link-local.

## Usage

    orin network
    orin network --json
"""

_PROCESSES = """\
# orin processes

Top processes by resident memory (`VmRSS`), read straight from `/proc` — no
`ps` dependency. RSS is the right lens on a unified-memory board: the share of
the one shared pool a process holds resident. Kernel threads (no `VmRSS`) are
skipped.

## Usage

    orin processes
    orin processes --json
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
    ("status",): _STATUS,
    ("memory",): _MEMORY,
    ("gpu",): _GPU,
    ("disk",): _DISK,
    ("thermal",): _THERMAL,
    ("containers",): _CONTAINERS,
    ("network",): _NETWORK,
    ("processes",): _PROCESSES,
}
