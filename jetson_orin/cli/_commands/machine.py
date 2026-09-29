"""Registration for the host-telemetry leaf verbs.

Jetson Orin *is* the system, so the machine-scope verbs sit at the top level
alongside ``whoami``/``doctor`` rather than under a noun:

    orin status       machine-wide scope, anomalies first (the headline)
    orin memory       unified RAM + swap
    orin gpu          Ampere iGPU snapshot (nvidia-smi + sysfs backfill)
    orin disk         filesystem usage
    orin thermal      SoC thermal zones + hwmon sensors
    orin containers   running Docker containers + health
    orin network      interfaces, routes, reachable addresses
    orin processes    top processes by resident memory

Each is a thin ``--json``-supporting leaf verb backed by a collector in
:mod:`jetson_orin.probe` (see :mod:`jetson_orin.cli._commands._probe`). All are
descriptive: a missing subsystem reports ``available: false`` and still exits
0.
"""

from __future__ import annotations

import argparse

from jetson_orin.cli._commands._probe import register_probe
from jetson_orin.probe import (
    containers,
    disk,
    gpu,
    memory,
    network,
    processes,
    status,
    thermal,
)

# (verb, collector, help) — order is the help-listing order.
_VERBS = [
    ("status", status.collect, "Machine-wide scope, anomalies first (the headline)."),
    ("memory", memory.collect, "Unified RAM + swap (memory shared by CPU and GPU)."),
    ("gpu", gpu.collect, "Jetson Orin iGPU: utilization, temp, power, GPU processes."),
    ("disk", disk.collect, "Filesystem usage for real (non-virtual) block devices."),
    ("thermal", thermal.collect, "SoC thermal zones and hwmon sensors (Celsius)."),
    ("containers", containers.collect, "Running Docker containers and their health."),
    ("network", network.collect, "Interfaces, default route, and reachable addresses."),
    ("processes", processes.collect, "Top processes by resident memory."),
]


def register(sub: argparse._SubParsersAction) -> None:
    for name, collect, help_text in _VERBS:
        register_probe(sub, name, collect, help_text)
