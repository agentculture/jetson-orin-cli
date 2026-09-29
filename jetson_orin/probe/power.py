"""``orin power`` — nvpmodel mode, jetson_clocks state, and per-rail power draw.

Jetson AGX Orin exposes power posture through three independent sources, each
read on its own and reported on its own (measured on L4T R39.2.0):

* ``nvpmodel -q`` — the active power mode (``NV Power Mode: MAXN`` then the
  mode id on the next line). Readable without root.
* ``jetson_clocks --show`` — whether CPU/GPU clocks are pinned to max. It needs
  root (``Error: Run this script(...) as a root user``, exit 1), so a normal
  user gets ``available: false`` plus a remediation, never a guess. This probe
  never runs ``jetson_clocks`` without ``--show`` and never calls ``nvpmodel -m``.
* ``ina3221`` power monitors under ``/sys/class/hwmon`` — rail telemetry that
  needs no privilege. Only channels that carry an ``in{n}_label`` *and* a
  ``curr{n}_input`` are rails (Orin has two chips; the second labels only one
  of its channels, and ``in7`` "sum of shunt voltages" has no current node).
  Power is ``in{n}_input`` (mV) x ``curr{n}_input`` (mA) / 1000 -> mW.

The overall report is only ``unavailable`` when none of the three yielded
anything.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from jetson_orin.probe import _run
from jetson_orin.probe._report import report, unavailable
from jetson_orin.probe._run import Runner, default_runner

_INA_PREFIX = "ina"

_NVPMODEL_HINT = "install nvpmodel (nvidia-l4t-nvpmodel) and ensure `nvpmodel -q` is readable"
_CLOCKS_HINT = "jetson_clocks --show needs root: run `sudo jetson_clocks --show`"


def _parse_nvpmodel(out: Optional[str]) -> dict:
    """Parse ``nvpmodel -q`` output, e.g. ``"NV Power Mode: MAXN\\n0\\n"``."""
    if not out or not out.strip():
        return {"available": False, "mode": None, "mode_id": None, "raw": None}
    mode: Optional[str] = None
    mode_id: Optional[str] = None
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("nv power mode"):
            mode = stripped.partition(":")[2].strip() or None
        elif stripped.isdigit():
            mode_id = stripped
    return {"available": mode is not None, "mode": mode, "mode_id": mode_id, "raw": out.strip()}


def _parse_jetson_clocks(out: Optional[str]) -> dict:
    """``jetson_clocks --show`` output is kept raw (long, host-specific)."""
    if not out or not out.strip():
        return {"available": False, "raw": None}
    return {"available": True, "raw": out.strip()}


def _rail_power_mw(hdir: Path, idx: str) -> Optional[float]:
    """Power for channel ``idx``: ``power{idx}_input`` (uW) else mV x mA."""
    raw = _run.read_first_line(hdir / f"power{idx}_input")
    if raw:
        try:
            return int(raw) / 1000.0
        except ValueError:
            pass
    volt = _run.read_first_line(hdir / f"in{idx}_input")
    curr = _run.read_first_line(hdir / f"curr{idx}_input")
    if volt and curr:
        try:
            return int(volt) * int(curr) / 1000.0  # mV * mA / 1000 -> mW
        except ValueError:
            pass
    return None


def _chip_rails(hdir: Path) -> list[dict]:
    rails: list[dict] = []
    for label_path in sorted(hdir.glob("in*_label")):
        idx = label_path.name[len("in") : -len("_label")]
        label = _run.read_first_line(label_path)
        if not label:
            continue
        # No matching current node -> a diagnostic channel, not a power rail.
        if _run.read_first_line(hdir / f"curr{idx}_input") is None:
            continue
        rails.append({"label": label, "power_mw": _rail_power_mw(hdir, idx)})
    return rails


def _rails(hwmon_root: Path) -> list[dict]:
    if not hwmon_root.is_dir():
        return []
    rails: list[dict] = []
    for hdir in sorted(hwmon_root.glob("hwmon*"), key=lambda p: int(p.name[5:] or 0)):
        name = (_run.read_first_line(hdir / "name") or "").lower()
        if name.startswith(_INA_PREFIX):
            rails.extend(_chip_rails(hdir))
    return rails


def collect(runner: Optional[Runner] = None, hwmon_root: str = "/sys/class/hwmon") -> dict:
    """Return a power report (nvpmodel + jetson_clocks + hwmon rails)."""
    run = runner or default_runner

    nvpmodel = _parse_nvpmodel(run("nvpmodel", ["-q"]))
    if not nvpmodel["available"]:
        nvpmodel["remediation"] = _NVPMODEL_HINT
    clocks = _parse_jetson_clocks(run("jetson_clocks", ["--show"]))
    if not clocks["available"]:
        clocks["remediation"] = _CLOCKS_HINT
    rails = _rails(Path(hwmon_root))

    if not nvpmodel["available"] and not clocks["available"] and not rails:
        return unavailable(
            "power",
            "nvpmodel, jetson_clocks, hwmon",
            "run on a Jetson Orin; jetson_clocks needs root, and rail telemetry "
            "needs an ina3221 hwmon node",
        )

    sections = []
    if nvpmodel["available"]:
        item = f"mode: {nvpmodel['mode']}"
        if nvpmodel["mode_id"] is not None:
            item += f" (id {nvpmodel['mode_id']})"
        sections.append({"title": "Power mode", "items": [item]})
    else:
        sections.append(
            {"title": "Power mode", "items": [f"unavailable — {nvpmodel['remediation']}"]}
        )
    if clocks["available"]:
        sections.append({"title": "jetson_clocks", "items": [clocks["raw"].splitlines()[0]]})
    else:
        sections.append(
            {"title": "jetson_clocks", "items": [f"unavailable — {clocks['remediation']}"]}
        )
    if rails:
        items = [
            (
                f"{r['label']}: {r['power_mw']:.0f} mW"
                if r["power_mw"] is not None
                else f"{r['label']}: n/a"
            )
            for r in rails
        ]
        sections.append({"title": "Power rails", "items": items})

    return report(
        "power",
        source="nvpmodel, jetson_clocks, hwmon",
        sections=sections,
        data={"nvpmodel": nvpmodel, "jetson_clocks": clocks, "rails": rails},
    )
