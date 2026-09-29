"""Tests for ``orin power``: nvpmodel mode, jetson_clocks state, hwmon rails.

The fixtures mirror what was measured on an AGX Orin devkit (L4T R39.2.0):
two ina3221 chips (hwmon5 with three labelled rails, hwmon6 with one labelled
rail and unlabelled channels) plus a non-power chip.
"""

from __future__ import annotations

import json

from jetson_orin.cli import main
from jetson_orin.probe import power

_NVPMODEL_OUT = "NV Power Mode: MAXN\n0\n"
_JC_ERR = "Error: Run this script(/usr/bin/jetson_clocks) as a root user\n"
_JC_OK = "SOC family:tegra234  Machine:NVIDIA Jetson AGX Orin Developer Kit\nOnline CPUs: 0-11\n"


def _chan(chip, idx, label, volt, curr):
    if label is not None:
        (chip / f"in{idx}_label").write_text(label + "\n")
    (chip / f"in{idx}_input").write_text(f"{volt}\n")
    (chip / f"curr{idx}_input").write_text(f"{curr}\n")


def _hwmon(tmp_path):
    root = tmp_path / "hwmon"
    c5 = root / "hwmon5"
    c5.mkdir(parents=True)
    (c5 / "name").write_text("ina3221\n")
    _chan(c5, 1, "VDD_GPU_SOC", 4900, 2000)
    _chan(c5, 2, "VDD_CPU_CV", 4900, 1000)
    _chan(c5, 3, "VIN_SYS_5V0", 5000, 1600)
    (c5 / "in7_label").write_text("sum of shunt voltages\n")  # no curr7 -> skipped
    (c5 / "in7_input").write_text("1200\n")
    c6 = root / "hwmon6"
    c6.mkdir()
    (c6 / "name").write_text("ina3221\n")
    _chan(c6, 1, None, 5000, 10)  # unlabelled channel: never invented
    _chan(c6, 2, "VDDQ_VDD2_1V8AO", 1800, 500)
    other = root / "hwmon3"
    other.mkdir()
    (other / "name").write_text("nvme\n")
    return str(root)


def _runner(nvpmodel, jc):
    def run(name, args):
        if name == "nvpmodel":
            assert list(args) == ["-q"]
            return nvpmodel
        assert name == "jetson_clocks" and list(args) == ["--show"]
        return jc

    return run


def test_power_reports_mode_clocks_and_rails(tmp_path) -> None:
    rep = power.collect(runner=_runner(_NVPMODEL_OUT, _JC_OK), hwmon_root=_hwmon(tmp_path))
    assert rep["available"] is True
    d = rep["data"]
    assert d["nvpmodel"]["mode"] == "MAXN"
    assert d["nvpmodel"]["mode_id"] == "0"
    assert d["nvpmodel"]["raw"] == _NVPMODEL_OUT.strip()
    assert d["jetson_clocks"]["available"] is True
    assert d["jetson_clocks"]["raw"] == _JC_OK.strip()
    rails = {r["label"]: r["power_mw"] for r in d["rails"]}
    assert rails == {
        "VDD_GPU_SOC": 9800.0,
        "VDD_CPU_CV": 4900.0,
        "VIN_SYS_5V0": 8000.0,
        "VDDQ_VDD2_1V8AO": 900.0,
    }
    assert [s["title"] for s in rep["sections"]] == ["Power mode", "jetson_clocks", "Power rails"]


def test_power_jetson_clocks_root_only_degrades_with_remediation(tmp_path) -> None:
    # run_tool returns None on the non-zero exit jetson_clocks gives non-root.
    rep = power.collect(runner=_runner(_NVPMODEL_OUT, None), hwmon_root=_hwmon(tmp_path))
    assert rep["available"] is True
    jc = rep["data"]["jetson_clocks"]
    assert jc["available"] is False
    assert jc["raw"] is None
    assert "root" in jc["remediation"]
    assert rep["data"]["nvpmodel"]["available"] is True


def test_power_nvpmodel_unreadable_is_flagged_not_guessed(tmp_path) -> None:
    rep = power.collect(runner=_runner(None, None), hwmon_root=_hwmon(tmp_path))
    nv = rep["data"]["nvpmodel"]
    assert nv["available"] is False and nv["mode"] is None and nv["remediation"]
    assert rep["data"]["rails"]


def test_power_unavailable_when_nothing_readable(tmp_path) -> None:
    rep = power.collect(runner=lambda _n, _a: None, hwmon_root=str(tmp_path / "none"))
    assert rep["available"] is False
    assert rep["remediation"]


def test_power_unreadable_current_gives_null_power(tmp_path) -> None:
    root = _hwmon(tmp_path)
    (tmp_path / "hwmon" / "hwmon5" / "curr2_input").write_text("garbage\n")
    rep = power.collect(runner=_runner(_NVPMODEL_OUT, _JC_OK), hwmon_root=root)
    rails = {r["label"]: r["power_mw"] for r in rep["data"]["rails"]}
    assert rails["VDD_CPU_CV"] is None


def test_power_cli_json(capsys) -> None:
    assert main(["power", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "power"
    assert isinstance(payload["available"], bool)
    assert "data" in payload


def test_power_not_in_status_subsystems(capsys) -> None:
    assert main(["status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert sorted(payload["data"]["subsystems"]) == [
        "containers",
        "disk",
        "gpu",
        "memory",
        "network",
        "processes",
        "thermal",
    ]
