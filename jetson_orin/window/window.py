"""``window show|store|lock|restore`` and ``drop-caches`` (contract sections 1-5).

State lives in ``${XDG_STATE_HOME:-~/.local/state}/orin/``: ``window.json`` (the
marker: ``locked`` flag) and ``window-clocks.conf`` (the file
``jetson_clocks --store`` writes and ``--restore`` reads). Every privileged call
is ``sudo -n`` so a missing grant fails fast as ``not_granted`` and never prompts.

Orin assumptions (verified only against fakes, no read on a live box):
``jetson_clocks`` (no args) pins clocks to max, ``jetson_clocks --fan`` pins the fan
to max, and ``jetson_clocks --store/--restore`` round-trips clocks and fan PWM.
``fan_profile`` is read-only from ``nvfancontrol -q`` when available, else null.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from jetson_orin.probe import power as power_probe
from jetson_orin.window import grant
from jetson_orin.window._exec import Exec

JC = grant.JETSON_CLOCKS


def state_dir() -> str:
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local/state")
    return os.path.join(base, "orin")


def _state_path(sdir: str) -> Path:
    return Path(sdir) / "window.json"


def _clocks_path(sdir: str) -> str:
    return os.path.join(sdir, "window-clocks.conf")


def _load(sdir: str) -> Optional[dict]:
    try:
        return json.loads(_state_path(sdir).read_text())
    except (OSError, ValueError):
        return None


def _read_int(path: Path) -> Optional[int]:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def _mhz(hz: Optional[int]) -> Optional[int]:
    return None if hz is None else round(hz / 1_000_000)


def _clocks(sysroot: str) -> dict:
    gpu = next(iter(sorted(Path(sysroot, "class/devfreq").glob("*gpu*"))), None)
    emc = Path(sysroot, "kernel/debug/clk/emc/clk_rate")
    return {
        "gpu_mhz": _mhz(_read_int(gpu / "cur_freq")) if gpu else None,
        "gpu_min_mhz": _mhz(_read_int(gpu / "min_freq")) if gpu else None,
        "gpu_max_mhz": _mhz(_read_int(gpu / "max_freq")) if gpu else None,
        "emc_mhz": _mhz(_read_int(emc)),
    }


def _temps(sysroot: str) -> dict:
    out: dict = {}
    for zone in sorted(Path(sysroot, "class/thermal").glob("thermal_zone*")):
        try:
            name = (zone / "type").read_text().strip()
            out[name] = int((zone / "temp").read_text().strip()) / 1000.0
        except (OSError, ValueError, TypeError):
            continue
    return out


def _fan_profile(run: Exec) -> Optional[str]:
    res = run(["nvfancontrol", "-q"], None)
    if res is None or res[0] != 0:
        return None
    for line in res[1].splitlines():
        if "FAN_PROFILE" in line.upper() and ":" in line:
            return line.partition(":")[2].strip() or None
    return None


def show(run: Exec, *, sdir: Optional[str] = None, sysroot: str = "/sys") -> dict:
    sdir = sdir or state_dir()
    state = _load(sdir)
    mode = power_probe._parse_nvpmodel(
        (lambda r: r[1] if r and r[0] == 0 else None)(run(["nvpmodel", "-q"], None))
    )
    return {
        "ok": True,
        "reason": None,
        "active": bool(state and state.get("locked")),
        "stored": state is not None,
        "supported": True,
        "power_mode": mode["mode"],
        "clocks": _clocks(sysroot),
        "fan_profile": _fan_profile(run),
        "temps_c": _temps(sysroot),
        "detail": {"nvpmodel_id": mode["mode_id"], "state_file": str(_state_path(sdir))},
    }


def _fail(run: Exec, action: str, reason: str, code: int, message: str, **kw) -> tuple[dict, int]:
    rep = show(run, **kw)
    rep.update({"ok": False, "reason": reason, "action": action, "message": message})
    return rep, code


def _priv(run: Exec, argv: list[str]) -> tuple[Optional[str], str]:
    """Run ``sudo -n argv``. Returns ``(reason|None, message)``."""
    res = run(["sudo", "-n", *argv], None)
    if res is None:
        return "tool_missing", "sudo not found"
    rc, out, err = res
    if rc == 0:
        return None, ""
    text = (err or out).strip()
    if "password is required" in text or "not allowed" in text or "a terminal is required" in text:
        return "not_granted", text
    return "failed", text


def _need_tool(run: Exec) -> Optional[str]:
    # tool presence check without privilege: `jetson_clocks --help` is not run; use which-less probe
    return None if run(["jetson_clocks", "--help"], None) is not None else "tool_missing"


def act(
    run: Exec, action: str, *, sdir: Optional[str] = None, sysroot: str = "/sys"
) -> tuple[dict, int]:
    """Run ``store``, ``lock`` or ``restore``. Returns ``(report, exit_code)``."""
    sdir = sdir or state_dir()
    kw = {"sdir": sdir, "sysroot": sysroot}
    state = _load(sdir)

    if action == "restore" and state is None:
        rep = show(run, **kw)
        rep.update({"action": "restore", "restored": False})
        return rep, 0
    if action == "store" and state is not None and state.get("locked"):
        return _fail(run, action, "window_active", 1, "a window is active; restore first", **kw)
    if action == "lock" and state is None:
        return _fail(run, action, "no_stored_state", 1, "run `orin window store` first", **kw)
    if _need_tool(run):
        return _fail(run, action, "tool_missing", 2, "jetson_clocks not found", **kw)

    clocks = _clocks_path(sdir)
    if action == "store":
        os.makedirs(sdir, exist_ok=True)
        reason, msg = _priv(run, [JC, "--store", clocks])
        if reason is None:
            _state_path(sdir).write_text(json.dumps({"locked": False, "clocks_file": clocks}))
    elif action == "lock":
        reason, msg = _priv(run, [JC])
        if reason is None:
            reason, msg = _priv(run, [JC, "--fan"])
        if reason is None:
            _state_path(sdir).write_text(json.dumps({"locked": True, "clocks_file": clocks}))
    else:
        reason, msg = _priv(run, [JC, "--restore", clocks])
        if reason is None:
            for p in (_state_path(sdir), Path(clocks)):
                try:
                    p.unlink()
                except OSError:
                    pass
    if reason is not None:
        return _fail(run, action, reason, 2, msg, **kw)
    rep = show(run, **kw)
    rep["action"] = action
    if action == "restore":
        rep["restored"] = True
    return rep, 0


def drop_caches(run: Exec) -> tuple[dict, int]:
    rule = grant.drop_caches_rule(grant.listing(run))
    if rule is None:
        return {"ok": False, "reason": "not_granted", "cleared": False, "rule": None}, 2
    run(["sync"], None)
    if rule == "tee":
        res = run(grant.TEE_ARGV, "3")
    else:
        res = run(grant.SYSCTL_ARGV, None)
    if res is None:
        return {"ok": False, "reason": "tool_missing", "cleared": False, "rule": rule}, 2
    if res[0] != 0:
        return {
            "ok": False,
            "reason": "failed",
            "cleared": False,
            "rule": rule,
            "message": (res[2] or res[1]).strip(),
        }, 2
    return {"ok": True, "reason": None, "cleared": True, "rule": rule}, 0
