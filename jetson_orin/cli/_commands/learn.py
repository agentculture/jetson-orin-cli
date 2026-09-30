"""``orin learn`` — the learnability affordance.

Prints a structured self-teaching prompt. Must satisfy the agent-first rubric:
>=200 chars and mention purpose, command map, exit codes, --json, and explain.
"""

from __future__ import annotations

import argparse

from jetson_orin import __version__
from jetson_orin.cli._output import emit_result

_TEXT = """\
jetson-orin-cli — the AgentCulture mesh agent for the NVIDIA Jetson AGX Orin.

Purpose
-------
Device CLI for the Jetson AGX Orin: read-only host telemetry (memory, gpu, disk,
thermal, containers, network, processes, power), a guarded swap manager, and a
deterministic threshold watchdog (monitor). It is an agent-first CLI (cited from
the teken `python-cli` reference) with a Culture mesh identity (culture.yaml).

Commands
--------
  orin whoami             Identity from culture.yaml.
  orin learn              This self-teaching prompt.
  orin explain <path>...  Markdown docs for any noun/verb path.
  orin overview           Descriptive snapshot of the agent.
  orin doctor             Check the agent-identity invariants.
  orin cli overview       Describe the CLI surface itself.
  orin swap               Swap status, per-process history, guarded grow.
  orin monitor            AI-free threshold watchdog that webhooks on alerts.

Machine scope (Jetson Orin host telemetry)
------------------------------------------
  orin status             Machine-wide scope, anomalies first (the headline;
                           includes the L4T version).
  orin memory             Unified RAM + swap (CPU and iGPU share it).
  orin gpu                Ampere iGPU: util, temp, power, processes
                           (nvidia-smi backfilled from sysfs).
  orin disk               Filesystem usage for real block devices.
  orin thermal            SoC thermal zones and hwmon sensors.
  orin containers         Running Docker containers and health.
  orin network            Interfaces, routes, reachable addresses.
  orin processes          Top processes by resident memory.
  orin power              nvpmodel mode, jetson_clocks state, per-rail power.
These are read-only and exit 0 even when a subsystem is absent (the report
carries available:false plus a remediation hint); doctor is the health gate.

Machine-readable output
-----------------------
Every command supports --json. Errors in JSON mode emit
{"code", "message", "remediation"} to stderr. Stdout and stderr never mix.

Exit-code policy
----------------
  0 success
  1 user-input error (bad flag, bad path, missing arg)
  2 environment / setup error
  3+ reserved

More detail
-----------
  orin explain orin
"""


def _as_json_payload() -> dict[str, object]:
    return {
        "tool": "jetson-orin-cli",
        "version": __version__,
        "purpose": "Device CLI and mesh agent for the NVIDIA Jetson AGX Orin.",
        "commands": [
            {"path": ["whoami"], "summary": "Identity probe from culture.yaml."},
            {"path": ["learn"], "summary": "Self-teaching prompt."},
            {"path": ["explain"], "summary": "Markdown docs by path."},
            {"path": ["overview"], "summary": "Descriptive snapshot of the agent."},
            {"path": ["doctor"], "summary": "Check the agent-identity invariants."},
            {"path": ["cli", "overview"], "summary": "Describe the CLI surface."},
            {"path": ["status"], "summary": "Machine-wide scope, anomalies first."},
            {"path": ["memory"], "summary": "Unified RAM + swap."},
            {"path": ["gpu"], "summary": "Ampere iGPU snapshot."},
            {"path": ["disk"], "summary": "Filesystem usage."},
            {"path": ["thermal"], "summary": "SoC thermal zones and hwmon sensors."},
            {"path": ["containers"], "summary": "Running Docker containers and health."},
            {"path": ["network"], "summary": "Interfaces, routes, reachable addresses."},
            {"path": ["processes"], "summary": "Top processes by resident memory."},
            {"path": ["power"], "summary": "nvpmodel mode, jetson_clocks state, rail power."},
            {"path": ["swap"], "summary": "Swap status, history, guarded grow."},
            {"path": ["monitor"], "summary": "Threshold watchdog that webhooks on alerts."},
        ],
        "exit_codes": {
            "0": "success",
            "1": "user-input error",
            "2": "environment/setup error",
        },
        "json_support": True,
        "explain_pointer": "orin explain <path>...",
    }


def cmd_learn(args: argparse.Namespace) -> int:
    if getattr(args, "json", False):
        emit_result(_as_json_payload(), json_mode=True)
    else:
        emit_result(_TEXT, json_mode=False)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "learn",
        help="Print a structured self-teaching prompt for agent consumers.",
    )
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_learn)
