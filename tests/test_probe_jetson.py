"""Unit tests for the Jetson-specific probes: gpu's sysfs fallback, l4t.

Every collector takes an injectable runner and/or file root, so these tests
run deterministically off real Jetson Orin hardware (fixtures built in
``tmp_path`` mirror what was observed live on a Orin devkit: thin
``nvidia-smi`` NVML fields, ``/sys/class/devfreq`` GPU clocks, INA3221/INA238
hwmon rails, and ``/etc/nv_tegra_release``).
"""

from __future__ import annotations

from jetson_orin.probe import gpu, l4t, status

# --- gpu: sysfs fixture builder --------------------------------------------


def _write_gpu_sysfs(tmp_path, *, cur_hz="315000000", max_hz="1575000000"):
    """Build devfreq/thermal/hwmon fixtures matching what Orin exposes live."""
    devfreq = tmp_path / "devfreq"
    (devfreq / "gpu-gpc-0").mkdir(parents=True)
    (devfreq / "gpu-gpc-0" / "cur_freq").write_text(cur_hz + "\n")
    (devfreq / "gpu-gpc-0" / "max_freq").write_text(max_hz + "\n")

    thermal = tmp_path / "thermal"
    (thermal / "thermal_zone1").mkdir(parents=True)
    (thermal / "thermal_zone1" / "type").write_text("gpu-thermal\n")
    (thermal / "thermal_zone1" / "temp").write_text("48406\n")

    hwmon = tmp_path / "hwmon"
    (hwmon / "hwmon5").mkdir(parents=True)
    (hwmon / "hwmon5" / "name").write_text("ina3221\n")
    (hwmon / "hwmon5" / "in1_label").write_text("VDD_GPU\n")
    (hwmon / "hwmon5" / "in1_input").write_text("19864\n")
    (hwmon / "hwmon5" / "curr1_input").write_text("20\n")

    return str(devfreq), str(thermal), str(hwmon)


# --- gpu: nvidia-smi is thin on Orin (name+utilization only) --------------

# Real line captured on a Jetson Orin devkit: only name/utilization.* are
# populated; temperature/power/memory/clocks/fan all come back [N/A].
_THIN_SMI_LINE = "NVIDIA Orin, 0, 0, [N/A], [N/A], [N/A], [N/A], [N/A], [N/A], [N/A]\n"
_FULL_SMI_LINE = "NVIDIA Orin, 12, 3, 55, 20.5, 60, [N/A], [N/A], 900, [N/A]\n"


def _smi_runner(line: str):
    def _run(name: str, args) -> str:
        assert name == "nvidia-smi"
        if "--query-gpu" in " ".join(args):
            return line
        if "--query-compute-apps" in " ".join(args):
            return ""
        return ""

    return _run


def test_gpu_full_nvidia_smi_needs_no_sysfs_fallback(tmp_path) -> None:
    devfreq, thermal, hwmon = _write_gpu_sysfs(tmp_path)
    rep = gpu.collect(
        runner=_smi_runner(_FULL_SMI_LINE),
        devfreq_root=devfreq,
        thermal_root=thermal,
        hwmon_root=hwmon,
    )
    assert rep["available"] is True
    assert rep["source"] == "nvidia-smi"
    assert rep["data"]["sysfs_augmented_fields"] == []
    assert rep["data"]["gpu"]["temperature.gpu"] == "55"


def test_gpu_thin_nvidia_smi_falls_back_to_sysfs_for_missing_fields(tmp_path) -> None:
    devfreq, thermal, hwmon = _write_gpu_sysfs(tmp_path)
    rep = gpu.collect(
        runner=_smi_runner(_THIN_SMI_LINE),
        devfreq_root=devfreq,
        thermal_root=thermal,
        hwmon_root=hwmon,
    )
    assert rep["available"] is True
    assert rep["source"] == "nvidia-smi+sysfs"
    filled = set(rep["data"]["sysfs_augmented_fields"])
    assert filled == {"temperature.gpu", "power.draw", "clocks.sm"}
    vals = rep["data"]["gpu"]
    assert vals["temperature.gpu"] == "48.4"
    assert vals["clocks.sm"] == "315"
    assert float(vals["power.draw"]) > 0
    # utilization came straight from nvidia-smi and must be left untouched.
    assert vals["utilization.gpu"] == "0"
    # A GPU report at 48.4 C is nowhere near the hot threshold.
    assert rep["warnings"] == []


def test_gpu_thin_nvidia_smi_without_any_sysfs_stays_nvidia_smi_only(tmp_path) -> None:
    rep = gpu.collect(
        runner=_smi_runner(_THIN_SMI_LINE),
        devfreq_root=str(tmp_path / "no-devfreq"),
        thermal_root=str(tmp_path / "no-thermal"),
        hwmon_root=str(tmp_path / "no-hwmon"),
    )
    assert rep["available"] is True
    assert rep["source"] == "nvidia-smi"
    assert rep["data"]["sysfs_augmented_fields"] == []
    assert rep["data"]["gpu"]["temperature.gpu"] is None


def test_gpu_absent_nvidia_smi_uses_sysfs(tmp_path) -> None:
    devfreq, thermal, hwmon = _write_gpu_sysfs(tmp_path)
    rep = gpu.collect(
        runner=lambda _n, _a: None,
        devfreq_root=devfreq,
        thermal_root=thermal,
        hwmon_root=hwmon,
    )
    assert rep["available"] is True
    assert rep["source"] == "sysfs"
    data = rep["data"]["gpu"]
    assert data["clock_mhz"] == 315.0
    assert data["clock_pct_of_max"] == 20.0
    assert data["temperature_c"] == 48.406
    assert data["power_w"] is not None
    titles = [s["title"] for s in rep["sections"]]
    assert "GPU (sysfs)" in titles


def test_gpu_fully_degraded_when_neither_available(tmp_path) -> None:
    rep = gpu.collect(
        runner=lambda _n, _a: None,
        devfreq_root=str(tmp_path / "no-devfreq"),
        thermal_root=str(tmp_path / "no-thermal"),
        hwmon_root=str(tmp_path / "no-hwmon"),
    )
    assert rep["available"] is False
    assert rep["remediation"]
    assert "nvidia-smi" in rep["source"]
    assert "sysfs" in rep["source"]


# --- l4t ---------------------------------------------------------------

# Real first line captured on a Jetson Orin devkit (/etc/nv_tegra_release).
_NV_TEGRA_RELEASE = (
    "# R38 (release), REVISION: 2.2, GCID: 42205042, BOARD: generic, "
    "EABI: aarch64, DATE: Thu Sep 25 22:47:11 UTC 2025\n"
    "# KERNEL_VARIANT: oot\n"
    "TARGET_USERSPACE_LIB_DIR=nvidia\n"
)


def test_l4t_parses_real_release_line(tmp_path) -> None:
    path = tmp_path / "nv_tegra_release"
    path.write_text(_NV_TEGRA_RELEASE)
    rep = l4t.collect(str(path))
    assert rep["available"] is True
    data = rep["data"]
    assert data["l4t"] == "R38.2.2"
    assert data["release"] == "R38"
    assert data["revision"] == "2.2"
    assert data["gcid"] == "42205042"
    assert data["board"] == "generic"
    assert data["eabi"] == "aarch64"
    assert data["date"] == "Thu Sep 25 22:47:11 UTC 2025"
    assert "R38.2.2" in " ".join(rep["sections"][0]["items"])


def test_l4t_unavailable_when_file_absent(tmp_path) -> None:
    rep = l4t.collect(str(tmp_path / "no-such-nv_tegra_release"))
    assert rep["available"] is False
    assert rep["remediation"]


def test_l4t_unavailable_on_malformed_content(tmp_path) -> None:
    path = tmp_path / "nv_tegra_release"
    path.write_text("not a tegra release file\n")
    rep = l4t.collect(str(path))
    assert rep["available"] is False
    assert rep["remediation"]


# --- l4t folded into status ------------------------------------------------


def test_status_includes_l4t_when_present(tmp_path) -> None:
    path = tmp_path / "nv_tegra_release"
    path.write_text(_NV_TEGRA_RELEASE)
    rep = status.collect(runner=lambda _n, _a: None, l4t_path=str(path))
    assert rep["data"]["host"]["l4t"] == "R38.2.2"


def test_status_l4t_is_none_off_jetson(tmp_path) -> None:
    rep = status.collect(
        runner=lambda _n, _a: None, l4t_path=str(tmp_path / "no-such-nv_tegra_release")
    )
    assert rep["data"]["host"]["l4t"] is None


# --- Orin-specific gpu sysfs layout ------------------------------------------
# Measured on a Jetson AGX Orin devkit (L4T R39.2.0): the GPU devfreq node is
# named "17000000.gpu" (no "gpc"), its utilization is exposed as permille in
# <devfreq node>/device/load (nvidia-smi reports [N/A]), and the GPU rail on
# the INA3221 is labeled "VDD_GPU_SOC" (GPU and SoC share one rail).

_ORIN_SMI_LINE = "Orin (nvgpu), [N/A], [N/A], [N/A], [N/A], [N/A], [N/A], [N/A], [N/A], [N/A]\n"


def _write_orin_gpu_sysfs(tmp_path, *, load="250"):
    node = tmp_path / "devfreq" / "17000000.gpu"
    (node / "device").mkdir(parents=True)
    (node / "cur_freq").write_text("1300500000\n")
    (node / "max_freq").write_text("1300500000\n")
    (node / "device" / "load").write_text(load + "\n")

    thermal = tmp_path / "thermal" / "thermal_zone1"
    thermal.mkdir(parents=True)
    (thermal / "type").write_text("gpu-thermal\n")
    (thermal / "temp").write_text("52187\n")

    chip = tmp_path / "hwmon" / "hwmon5"
    chip.mkdir(parents=True)
    (chip / "name").write_text("ina3221\n")
    (chip / "in1_label").write_text("VDD_GPU_SOC\n")
    (chip / "in1_input").write_text("19912\n")
    (chip / "curr1_input").write_text("240\n")
    return str(tmp_path / "devfreq"), str(tmp_path / "thermal"), str(tmp_path / "hwmon")


def test_gpu_orin_layout_backfills_util_power_clock_temp(tmp_path) -> None:
    devfreq, thermal, hwmon = _write_orin_gpu_sysfs(tmp_path)
    rep = gpu.collect(
        runner=_smi_runner(_ORIN_SMI_LINE),
        devfreq_root=devfreq,
        thermal_root=thermal,
        hwmon_root=hwmon,
    )
    assert rep["available"] is True
    assert rep["source"] == "nvidia-smi+sysfs"
    vals = rep["data"]["gpu"]
    assert vals["utilization.gpu"] == "25"
    assert vals["clocks.sm"] == "1300"
    assert vals["temperature.gpu"] == "52.2"
    assert abs(float(vals["power.draw"]) - 19912 * 240 / 1_000_000.0) < 0.01
    assert set(rep["data"]["sysfs_augmented_fields"]) == {
        "utilization.gpu",
        "temperature.gpu",
        "power.draw",
        "clocks.sm",
    }


def test_gpu_orin_sysfs_only_reports_load(tmp_path) -> None:
    devfreq, thermal, hwmon = _write_orin_gpu_sysfs(tmp_path)
    rep = gpu.collect(
        runner=lambda _n, _a: None,
        devfreq_root=devfreq,
        thermal_root=thermal,
        hwmon_root=hwmon,
    )
    assert rep["source"] == "sysfs"
    assert rep["data"]["gpu"]["utilization_pct"] == 25.0
    assert rep["data"]["gpu"]["power_w"] is not None


def test_gpu_util_backfilled_from_devfreq_when_smi_has_other_fields(tmp_path) -> None:
    # nvidia-smi supplies temperature/power/clock but utilization is [N/A]:
    # utilization must still come from devfreq load, and smi values stay.
    devfreq, thermal, hwmon = _write_orin_gpu_sysfs(tmp_path, load="400")
    line = "NVIDIA Orin, [N/A], [N/A], 55, 20.5, 60, [N/A], [N/A], 900, [N/A]\n"
    rep = gpu.collect(
        runner=_smi_runner(line),
        devfreq_root=devfreq,
        thermal_root=thermal,
        hwmon_root=hwmon,
    )
    vals = rep["data"]["gpu"]
    assert vals["utilization.gpu"] == "40"
    assert vals["temperature.gpu"] == "55"
    assert vals["clocks.sm"] == "900"
    assert rep["data"]["sysfs_augmented_fields"] == ["utilization.gpu"]
    assert rep["source"] == "nvidia-smi+sysfs"
