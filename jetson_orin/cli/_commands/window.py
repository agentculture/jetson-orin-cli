"""``orin window``, ``orin drop-caches``, ``orin grant-permissions``.

The machine-CLI window contract (lobes-cli ``docs/contracts/machine-cli-window.md``).
With ``--json`` stdout carries exactly ONE object with ``ok``/``reason``; a refused
or failed verb still emits that object and returns the contract exit code (1 refused
by state / declined, 2 environment), with a one-line diagnostic on stderr.
"""

from __future__ import annotations

import argparse
import sys
from typing import Callable

from jetson_orin.cli._output import emit_diagnostic, emit_result
from jetson_orin.window import grant
from jetson_orin.window import window as win
from jetson_orin.window._exec import Exec, default_exec

# Test seams (monkeypatched): the executor, an interactive-consent reader.
_exec: Exec = default_exec
_confirm: Callable[[str], bool] = lambda prompt: (  # noqa: E731
    sys.stdin.isatty() and input(prompt).strip().lower() in ("y", "yes")
)


def _run(argv, stdin=None):
    return _exec(argv, stdin)


def _text(rep: dict) -> str:
    lines = [f"ok: {rep.get('ok')}  reason: {rep.get('reason')}"]
    for k, v in rep.items():
        if k not in ("ok", "reason", "detail"):
            lines.append(f"{k}: {v}")
    return "\n".join(lines)


def _emit(rep: dict, code: int, args) -> int:
    json_mode = bool(getattr(args, "json", False))
    emit_result(rep if json_mode else _text(rep), json_mode=json_mode)
    if not rep.get("ok"):
        emit_diagnostic(f"error: {rep.get('reason')}: {rep.get('message', '')}".rstrip(": "))
    return code


def _cmd_window(args) -> int:
    if args.window_verb == "show":
        return _emit(win.show(_run), 0, args)
    rep, code = win.act(_run, args.window_verb)
    return _emit(rep, code, args)


def _cmd_drop(args) -> int:
    rep, code = win.drop_caches(_run)
    return _emit(rep, code, args)


def _cmd_grant(args) -> int:
    status = grant.check(_run)
    if args.check:
        return _emit(status, 0, args)
    sdir = win.state_dir()
    rules = grant.plan(status, sdir)
    if not rules:
        status["installed"] = False
        return _emit(status, 0, args)
    emit_diagnostic("rules to install in " + grant.SUDOERS_DEST + ":")
    for r in rules:
        emit_diagnostic("  " + r)
    if not args.yes and not _confirm("install these passwordless sudo rules? [y/N] "):
        status.update({"ok": False, "reason": "declined", "installed": False, "rules": rules})
        return _emit(status, 1, args)
    ok, detail = grant.install(_run, rules)
    if not ok:
        reason = "tool_missing" if detail.startswith("tool_missing") else "failed"
        status.update(
            {"ok": False, "reason": reason, "installed": False, "rules": rules, "message": detail}
        )
        return _emit(status, 2, args)
    after = grant.check(_run)
    after.update({"installed": True, "rules": rules, "path": detail})
    return _emit(after, 0, args)


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("window", help="Benchmark window: show/store/lock/restore clocks + fan.")
    wsub = p.add_subparsers(dest="window_verb", required=True, parser_class=type(p))
    for verb, text in (
        ("show", "Report clock/fan/power state and whether a window is active."),
        ("store", "Save the current clock/fan state (jetson_clocks --store)."),
        ("lock", "Lock clocks and fan to max (needs a stored state)."),
        ("restore", "Return to the stored state, then delete it."),
    ):
        v = wsub.add_parser(verb, help=text)
        v.add_argument("--json", action="store_true", help="Emit structured JSON.")
        v.set_defaults(func=_cmd_window)

    d = sub.add_parser("drop-caches", help="sync, then clear the page cache (granted sudo only).")
    d.add_argument("--json", action="store_true", help="Emit structured JSON.")
    d.set_defaults(func=_cmd_drop)

    g = sub.add_parser(
        "grant-permissions", help="Install the passwordless sudo rules window/drop-caches need."
    )
    g.add_argument("--check", action="store_true", help="Only report; install nothing.")
    g.add_argument("--yes", action="store_true", help="Install without the consent prompt.")
    g.add_argument("--json", action="store_true", help="Emit structured JSON.")
    g.set_defaults(func=_cmd_grant)
