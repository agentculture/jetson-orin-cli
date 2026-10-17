"""Passwordless-sudo grant detection and install (contract section 4).

Cited from mjolnir's ``cachectl.py`` (cite-don't-import). Detection is
``sudo -n -l`` (read-only, never prompts). An existing equivalent rule is reused;
``NOPASSWD: ALL`` counts as granted (``rule: "all"``) and is never installed.
Install writes a temp file, validates it with ``visudo -cf`` and places it with
ONE ``sudo install -m 0440 -o root -g root`` into ``/etc/sudoers.d/orin-lobes``.
"""

from __future__ import annotations

import getpass
import os
import re
import tempfile
from typing import Optional

from jetson_orin.window._exec import Exec

SUDOERS_DEST = "/etc/sudoers.d/orin-lobes"
SYSCTL_ARGV = ["sudo", "-n", "/usr/sbin/sysctl", "-w", "vm.drop_caches=3"]
TEE_ARGV = ["sudo", "-n", "tee", "/proc/sys/vm/drop_caches"]
JETSON_CLOCKS = "/usr/bin/jetson_clocks"

_ALL_RE = re.compile(r"NOPASSWD:\s*ALL\b")
_SYSCTL_RE = re.compile(r"sysctl.*vm\.drop_caches")
_TEE_RE = re.compile(r"tee /proc/sys/vm/drop_caches")


def listing(run: Exec) -> Optional[str]:
    """``sudo -n -l`` stdout, or ``None`` when sudo is missing or refuses."""
    res = run(["sudo", "-n", "-l"], None)
    if res is None or res[0] != 0:
        return None
    return res[1]


def drop_caches_rule(text: Optional[str]) -> Optional[str]:
    """Return ``"sysctl"``, ``"tee"``, ``"all"`` or ``None`` for a sudo listing."""
    if not text:
        return None
    if _SYSCTL_RE.search(text):
        return "sysctl"
    if _TEE_RE.search(text):
        return "tee"
    if _ALL_RE.search(text):
        return "all"
    return None


def window_rule(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    if "jetson_clocks" in text:
        return "jetson_clocks"
    if _ALL_RE.search(text):
        return "all"
    return None


def check(run: Exec) -> dict:
    text = listing(run)
    dc = drop_caches_rule(text)
    win = window_rule(text)
    return {
        "ok": True,
        "reason": None,
        "drop_caches": {"granted": dc is not None, "rule": dc, "source": "sudo -n -l"},
        "window": {"granted": win is not None, "rule": win},
    }


def window_rules(state_dir: str) -> list[str]:
    """The exact sudoers command specs the window verbs need (printed before install)."""
    clocks = os.path.join(state_dir, "window-clocks.conf")
    return [
        JETSON_CLOCKS,
        f"{JETSON_CLOCKS} --fan",
        f"{JETSON_CLOCKS} --store {clocks}",
        f"{JETSON_CLOCKS} --restore {clocks}",
    ]


def _escape(spec: str) -> str:
    return spec.replace("=", "\\=")


def plan(status: dict, state_dir: str) -> list[str]:
    """Rules still missing given a :func:`check` result."""
    rules: list[str] = []
    if not status["drop_caches"]["granted"]:
        rules.append("/usr/sbin/sysctl -w vm.drop_caches=3")
    if not status["window"]["granted"]:
        rules.extend(window_rules(state_dir))
    return rules


def render_sudoers(user: str, rules: list[str]) -> str:
    return "".join(f"{user} ALL=(root) NOPASSWD: {_escape(r)}\n" for r in rules)


def install(run: Exec, rules: list[str], user: Optional[str] = None) -> tuple[bool, str]:
    """Validate with ``visudo -cf`` then install once. Returns ``(ok, detail)``."""
    body = render_sudoers(user or getpass.getuser(), rules)
    fd, path = tempfile.mkstemp(prefix="orin-lobes-", suffix=".sudoers")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(body)
        res = run(["visudo", "-cf", path], None)
        if res is None:
            return False, "tool_missing: visudo"
        if res[0] != 0:
            return False, f"visudo rejected the rule: {(res[2] or res[1]).strip()}"
        res = run(
            ["sudo", "install", "-m", "0440", "-o", "root", "-g", "root", path, SUDOERS_DEST],
            None,
        )
        if res is None:
            return False, "tool_missing: sudo"
        if res[0] != 0:
            return False, (res[2] or res[1]).strip() or "install failed"
        return True, SUDOERS_DEST
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
