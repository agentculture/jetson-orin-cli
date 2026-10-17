"""Tests for ``orin window|drop-caches|grant-permissions`` (fakes only, no real sudo)."""

from __future__ import annotations

import json
import os

import pytest

from jetson_orin.cli import main
from jetson_orin.cli._commands import window as wcmd
from jetson_orin.window import window as wmod

SYSCTL_LIST = (
    "User spark may run the following commands:\n"
    "    (root) NOPASSWD: /usr/sbin/sysctl -w vm.drop_caches\\=3\n"
)
TEE_LIST = "    (root) NOPASSWD: /usr/bin/tee /proc/sys/vm/drop_caches\n"
ALL_LIST = "    (ALL : ALL) NOPASSWD: ALL\n"
NO_LIST = "User spark may run the following commands:\n    (ALL) /usr/bin/ls\n"
WINDOW_LIST = (
    "    (root) NOPASSWD: /usr/bin/jetson_clocks, /usr/bin/jetson_clocks --fan\n" + SYSCTL_LIST
)


class Fake:
    """Records argv; answers by prefix. Missing tools listed in ``missing``."""

    def __init__(self, sudo_list=NO_LIST, missing=(), fail=None):
        self.calls: list[tuple[tuple, str | None]] = []
        self.sudo_list = sudo_list
        self.missing = set(missing)
        self.fail = fail or {}

    def __call__(self, argv, stdin=None):
        argv = tuple(argv)
        self.calls.append((argv, stdin))
        if argv[0] in self.missing:
            return None
        for prefix, res in self.fail.items():
            if argv[: len(prefix)] == prefix:
                return res
        if argv == ("sudo", "-n", "-l"):
            return (0, self.sudo_list, "")
        if argv[0] == "nvpmodel":
            return (0, "NV Power Mode: MAXN\n0\n", "")
        return (0, "", "")

    def argvs(self):
        return [c[0] for c in self.calls]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    fake = Fake()
    monkeypatch.setattr(wcmd, "_exec", fake)
    monkeypatch.setattr(wmod, "FAN_CONF", str(tmp_path / "no-such-nvfancontrol.conf"))
    return fake


def run(capsys, *argv):
    rc = main(list(argv) + ["--json"])
    out = capsys.readouterr()
    return rc, json.loads(out.out), out.err


def use(monkeypatch, fake):
    monkeypatch.setattr(wcmd, "_exec", fake)


# --- window --------------------------------------------------------------


def test_show_idle(env, capsys):
    rc, o, _ = run(capsys, "window", "show")
    assert rc == 0
    assert o["ok"] is True
    assert o["reason"] is None
    assert o["active"] is False
    assert o["stored"] is False
    assert o["supported"] is True
    assert o["power_mode"] == "MAXN"
    assert set(o["clocks"]) == {"gpu_mhz", "gpu_min_mhz", "gpu_max_mhz", "emc_mhz"}
    assert o["fan_profile"] is None  # unreadable -> null, never guessed
    assert not any(a[:2] == ("sudo", "-n") for a in env.argvs())  # show needs no root


def test_store_lock_restore_cycle(env, capsys, tmp_path):
    rc, o, _ = run(capsys, "window", "store")
    assert rc == 0
    assert o["action"] == "store"
    assert o["stored"] is True
    assert o["active"] is False
    clocks = str(tmp_path / ".local/state/orin/window-clocks.conf")
    assert ("sudo", "-n", "/usr/bin/jetson_clocks", "--store", clocks) in env.argvs()

    rc, o, _ = run(capsys, "window", "lock")
    assert rc == 0
    assert o["active"] is True
    assert o["action"] == "lock"
    assert ("sudo", "-n", "/usr/bin/jetson_clocks") in env.argvs()
    assert ("sudo", "-n", "/usr/bin/jetson_clocks", "--fan") in env.argvs()

    rc, o, _ = run(capsys, "window", "restore")
    assert rc == 0
    assert o["restored"] is True
    assert o["stored"] is False
    assert o["active"] is False
    assert ("sudo", "-n", "/usr/bin/jetson_clocks", "--restore", clocks) in env.argvs()


def test_lock_without_store_refused(env, capsys):
    rc, o, err = run(capsys, "window", "lock")
    assert rc == 1
    assert o["ok"] is False
    assert o["reason"] == "no_stored_state"
    assert "error:" in err
    assert not any(a[:2] == ("sudo", "-n") for a in env.argvs())


def test_store_while_active_refused(env, capsys):
    run(capsys, "window", "store")
    run(capsys, "window", "lock")
    n = len(env.calls)
    rc, o, _ = run(capsys, "window", "store")
    assert rc == 1
    assert o["reason"] == "window_active"
    assert not any(a[:2] == ("sudo", "-n") for a, _ in env.calls[n:])


def test_restore_without_state_is_ok(env, capsys):
    rc, o, _ = run(capsys, "window", "restore")
    assert rc == 0
    assert o["ok"] is True
    assert o["restored"] is False


def test_store_not_granted(env, monkeypatch, capsys):
    f = Fake(
        fail={("sudo", "-n", "/usr/bin/jetson_clocks"): (1, "", "sudo: a password is required")}
    )
    use(monkeypatch, f)
    rc, o, _ = run(capsys, "window", "store")
    assert rc == 2
    assert o["reason"] == "not_granted"
    assert o["stored"] is False


def test_tool_missing(env, monkeypatch, capsys):
    use(monkeypatch, Fake(missing={"jetson_clocks"}))
    rc, o, _ = run(capsys, "window", "store")
    assert rc == 2
    assert o["reason"] == "tool_missing"


def test_privileged_failure(env, monkeypatch, capsys):
    f = Fake(fail={("sudo", "-n", "/usr/bin/jetson_clocks"): (1, "", "boom")})
    use(monkeypatch, f)
    rc, o, _ = run(capsys, "window", "store")
    assert rc == 2
    assert o["reason"] == "failed"
    assert o["message"] == "boom"


# --- drop-caches ---------------------------------------------------------


def test_drop_caches_sysctl(env, monkeypatch, capsys):
    f = Fake(sudo_list=SYSCTL_LIST)
    use(monkeypatch, f)
    rc, o, _ = run(capsys, "drop-caches")
    assert (rc, o) == (0, {"ok": True, "reason": None, "cleared": True, "rule": "sysctl"})
    assert ("sudo", "-n", "/usr/sbin/sysctl", "-w", "vm.drop_caches=3") in f.argvs()
    assert f.argvs().index(("sync",)) < f.argvs().index(
        ("sudo", "-n", "/usr/sbin/sysctl", "-w", "vm.drop_caches=3")
    )


def test_drop_caches_tee_uses_stdin(env, monkeypatch, capsys):
    f = Fake(sudo_list=TEE_LIST)
    use(monkeypatch, f)
    rc, o, _ = run(capsys, "drop-caches")
    assert rc == 0
    assert o["rule"] == "tee"
    assert (("sudo", "-n", "tee", "/proc/sys/vm/drop_caches"), "3") in f.calls


def test_drop_caches_all(env, monkeypatch, capsys):
    use(monkeypatch, Fake(sudo_list=ALL_LIST))
    rc, o, _ = run(capsys, "drop-caches")
    assert rc == 0
    assert o["rule"] == "all"


def test_drop_caches_no_grant(env, capsys):
    rc, o, _ = run(capsys, "drop-caches")  # Orin's real listing (2026-10-17): no rule
    assert rc == 2
    assert o["reason"] == "not_granted"
    assert o["cleared"] is False
    assert ("sync",) not in env.argvs()


def test_drop_caches_failure(env, monkeypatch, capsys):
    f = Fake(
        sudo_list=SYSCTL_LIST,
        fail={("sudo", "-n", "/usr/sbin/sysctl"): (1, "", "read-only")},
    )
    use(monkeypatch, f)
    rc, o, _ = run(capsys, "drop-caches")
    assert rc == 2
    assert o["reason"] == "failed"


# --- grant-permissions ---------------------------------------------------


def test_grant_check_none(env, capsys):
    rc, o, _ = run(capsys, "grant-permissions", "--check")
    assert rc == 0
    assert o["ok"] is True
    assert o["drop_caches"] == {"granted": False, "rule": None, "source": "sudo -n -l"}
    assert o["window"] == {"granted": False, "rule": None}
    assert all(a[0] != "visudo" for a in env.argvs())


def test_grant_check_existing_sysctl(env, monkeypatch, capsys):
    use(monkeypatch, Fake(sudo_list=SYSCTL_LIST))
    rc, o, _ = run(capsys, "grant-permissions", "--check")
    assert o["drop_caches"]["granted"]
    assert o["drop_caches"]["rule"] == "sysctl"


def test_grant_existing_installs_nothing(env, monkeypatch, capsys):
    f = Fake(sudo_list=WINDOW_LIST)
    use(monkeypatch, f)
    rc, o, _ = run(capsys, "grant-permissions", "--yes")
    assert rc == 0
    assert o["installed"] is False
    assert all(a[0] != "visudo" and "install" not in a for a in f.argvs())


def test_grant_install_planned(env, capsys, monkeypatch):
    seen = {}

    def fake(argv, stdin=None):
        if argv[0] == "visudo":
            seen["body"] = open(argv[2]).read()
        return Fake.__call__(env, argv, stdin)

    use(monkeypatch, fake)
    rc, o, err = run(capsys, "grant-permissions", "--yes")
    assert rc == 0
    assert o["installed"] is True
    assert o["path"] == "/etc/sudoers.d/orin-lobes"
    assert "vm.drop_caches\\=3" in seen["body"]
    assert "ALL=(root) NOPASSWD: ALL" not in seen["body"]
    assert "/usr/bin/jetson_clocks --fan" in seen["body"]
    argvs = env.argvs()
    inst = [a for a in argvs if a[:2] == ("sudo", "install")]
    assert len(inst) == 1
    assert inst[0][2:8] == ("-m", "0440", "-o", "root", "-g", "root")
    assert inst[0][-1] == "/etc/sudoers.d/orin-lobes"
    assert [a[0] for a in argvs].index("visudo") < argvs.index(inst[0])
    assert "rules to install" in err  # printed before installing


def test_grant_declined(env, monkeypatch, capsys):
    monkeypatch.setattr(wcmd, "_confirm", lambda prompt: False)
    rc, o, _ = run(capsys, "grant-permissions")
    assert rc == 1
    assert o["reason"] == "declined"
    assert o["installed"] is False
    assert all(a[0] != "visudo" for a in env.argvs())


def test_grant_consent_accepted(env, monkeypatch, capsys):
    monkeypatch.setattr(wcmd, "_confirm", lambda prompt: True)
    rc, o, _ = run(capsys, "grant-permissions")
    assert rc == 0
    assert o["installed"] is True


def test_grant_visudo_rejects(env, monkeypatch, capsys):
    use(monkeypatch, Fake(fail={("visudo",): (1, "", "syntax error")}))
    rc, o, _ = run(capsys, "grant-permissions", "--yes")
    assert rc == 2
    assert o["reason"] == "failed"
    assert o["installed"] is False


def test_text_mode_and_explain(env, capsys):
    assert main(["window", "show"]) == 0
    assert "ok: True" in capsys.readouterr().out
    for path in (["window"], ["drop-caches"], ["grant-permissions"]):
        assert main(["explain", *path]) == 0


# --- clocks_locked / emc / fan profile (real Orin readings, 2026-10-17) ----------


def _node(root, name, cur, mn, mx):
    d = root / "class/devfreq" / name
    d.mkdir(parents=True)
    for f, v in (("cur_freq", cur), ("min_freq", mn), ("max_freq", mx)):
        (d / f).write_text(f"{v}\n")


def _orin_sysfs(tmp_path, gpu_min=1300500000):
    _node(tmp_path, "17000000.gpu", 1300500000, gpu_min, 1300500000)
    _node(tmp_path, "bwmgr", 3199000000, 3199000000, 3199000000)
    _node(tmp_path, "15340000.vic", 729600000, 115200000, 729600000)
    return str(tmp_path)


def test_clocks_locked_true_on_operator_jetson_clocks(tmp_path):
    rep = wmod.show(Fake(), sdir=str(tmp_path / "s"), sysroot=_orin_sysfs(tmp_path))
    assert rep["active"] is False  # no lobes window...
    assert rep["clocks_locked"] is True  # ...but the clocks are pinned
    assert rep["clocks"]["gpu_mhz"] == 1300
    assert rep["clocks"]["emc_mhz"] == 3199


def test_clocks_locked_false_when_gpu_range_open(tmp_path):
    rep = wmod.show(
        Fake(), sdir=str(tmp_path / "s"), sysroot=_orin_sysfs(tmp_path, gpu_min=306000000)
    )
    assert rep["clocks_locked"] is False
    assert rep["clocks"]["gpu_min_mhz"] == 306


def test_clocks_locked_false_when_emc_unpinned(tmp_path):
    root = _orin_sysfs(tmp_path)
    (tmp_path / "class/devfreq/bwmgr/min_freq").write_text("204000000\n")
    assert wmod.show(Fake(), sdir=str(tmp_path / "s"), sysroot=root)["clocks_locked"] is False


def test_clocks_locked_true_when_emc_unreadable(tmp_path):
    _node(tmp_path, "17000000.gpu", 1300500000, 1300500000, 1300500000)
    rep = wmod.show(Fake(), sdir=str(tmp_path / "s"), sysroot=str(tmp_path))
    assert rep["clocks_locked"] is True
    assert rep["clocks"]["emc_mhz"] is None


def test_clocks_locked_null_when_missing(tmp_path):
    rep = wmod.show(Fake(), sdir=str(tmp_path / "s"), sysroot=str(tmp_path))
    assert rep["clocks_locked"] is None


def test_fan_profile_from_conf(tmp_path):
    conf = tmp_path / "nvfancontrol.conf"
    conf.write_text("# c\nFAN_DEFAULT_PROFILE quiet\nFAN_DEFAULT_GOVERNOR pid\n")
    rep = wmod.show(Fake(), sdir=str(tmp_path / "s"), sysroot=str(tmp_path), fan_conf=str(conf))
    assert rep["fan_profile"] == "quiet"


def test_xdg_state_home_is_ignored_by_window_state(monkeypatch, tmp_path):
    from jetson_orin.window import window as win

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    expected = os.path.realpath(str(tmp_path / "home" / ".local" / "state" / "orin"))
    for xdg in ("../x", "rel/path", str(tmp_path / "xdg")):
        monkeypatch.setenv("XDG_STATE_HOME", xdg)
        assert win.state_dir() == expected


def test_state_lives_under_home_local_state(monkeypatch, tmp_path):
    from jetson_orin.window import window as win

    monkeypatch.setenv("HOME", str(tmp_path))
    assert win.state_dir() == os.path.realpath(str(tmp_path / ".local" / "state" / "orin"))
