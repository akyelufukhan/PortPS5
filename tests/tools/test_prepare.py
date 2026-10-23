"""Synthetic preparation tests for the local regression tooling.

No game content or compiled runtime is used. Relinker subprocesses are mocked;
directory links use real Windows junctions or POSIX symlinks to exercise path
safety. Each test owns its temporary tree and runs without shared mutable state.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import regress

REAL_RUN = subprocess.run
METADATA = {
    "titleId": "PPSA00000",
    "localizedParameters": {"en-US": {"titleName": "Synthetic fixture"}},
}


def directory_link(link, target):
    """Create a directory alias without Windows developer-mode privileges."""
    if os.name == "nt":
        REAL_RUN(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        link.symlink_to(target, target_is_directory=True)


@pytest.fixture
def prepared_inputs(tmp_path, monkeypatch):
    """Provide isolated placeholder inputs and a mock that captures full conversions."""
    repo = tmp_path / "repo"
    config = repo / "config"
    config.mkdir(parents=True)
    (config / "global.toml").write_text("schema=1\n", encoding="utf-8")
    (config / "games").mkdir()
    (config / "games" / "PPSA00000.toml").write_text("schema=1\n", encoding="utf-8")
    monkeypatch.setattr(regress, "ROOT", repo)
    dump = tmp_path / "dump dir [x]"
    (dump / "sce_sys").mkdir(parents=True)
    (dump / "eboot.elf").write_bytes(b"synthetic")
    (dump / "sce_sys" / "param.json").write_text(json.dumps(METADATA), encoding="utf-8")
    libs = tmp_path / "runtime libs"
    libs.mkdir()
    for name in regress.REQUIRED_RUNTIME_FILES:
        (libs / name).write_bytes(b"synthetic runtime")
    relinker = tmp_path / "relinker.exe"
    relinker.write_bytes(b"synthetic tool")
    calls = []

    def run(command, **kwargs):
        """Simulate conversion; real junction creation still tests the Windows branch."""
        if command[0] == "powershell.exe":
            return REAL_RUN(command, **kwargs)
        calls.append((command, kwargs))
        Path(command[-1]).write_bytes(b"synthetic converted output")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(regress.subprocess, "run", run)
    return {
        "dump": dump,
        "libs": libs,
        "config": config,
        "relinker": relinker,
        "install": tmp_path / "install dir [x]",
        "calls": calls,
    }


def prepare_cli(inputs, **overrides):
    """Build the public CLI with optional path/flag overrides."""
    options = {name: inputs[name] for name in ("dump", "libs", "relinker", "install")}
    options.update(overrides)
    command = ["prepare"]
    for name, value in options.items():
        if value is True:
            command.append("--" + name)
        elif value is not None:
            command.extend(("--" + name, str(value)))
    return command


def assert_preflight_failure(inputs, capsys, **overrides):
    """Require a clean error before invoking conversion or creating the install."""
    assert regress.main(prepare_cli(inputs, **overrides)) == 1
    assert inputs["calls"] == []
    assert not inputs["install"].exists()
    return capsys.readouterr().err


def test_prepare_seeds_config_runtime_and_real_app0_link(prepared_inputs):
    inputs = prepared_inputs
    assert regress.main(prepare_cli(inputs)) == 0
    install = inputs["install"]
    assert (install / "game.exe").is_file()
    assert (install / "app0").resolve() == inputs["dump"]
    assert regress.is_path_link(install / "app0")
    assert not (install / "eboot.elf").exists()
    for name in regress.REQUIRED_RUNTIME_FILES:
        assert (install / "libs" / name).read_bytes() == b"synthetic runtime"
    assert (install / "config" / "global.toml").read_text() == "schema=1\n"
    command, kwargs = inputs["calls"][0]
    assert command == [
        str(inputs["relinker"]),
        "--windows",
        str(inputs["dump"] / "eboot.elf"),
        str(install / "game.exe"),
    ]
    assert kwargs == {"check": True, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}


def test_prepare_preserves_shell_metacharacters_in_paths(prepared_inputs, monkeypatch):
    # The literal %NAME%, ampersand, apostrophe and brackets must survive link
    # creation; neither cmd expansion nor PowerShell expression evaluation is allowed.
    inputs = prepared_inputs
    monkeypatch.setenv("PORTPS5_PATH_FIXTURE", "expanded-wrongly")
    dump = inputs["dump"].with_name("dump&%PORTPS5_PATH_FIXTURE%'[x]")
    inputs["dump"].rename(dump)
    inputs["dump"] = dump
    inputs["install"] = dump.with_name("install&%PORTPS5_PATH_FIXTURE%'[x]")
    assert regress.main(prepare_cli(inputs)) == 0
    assert (inputs["install"] / "app0").resolve() == dump


def test_prepare_preserves_custom_config_and_seeds_missing_files(prepared_inputs):
    inputs = prepared_inputs
    cli = prepare_cli(inputs)
    assert regress.main(cli) == 0
    config = inputs["install"] / "config"
    (config / "global.toml").write_bytes(b"custom global")
    (config / "games" / "PPSA00000.toml").write_bytes(b"custom per-title")
    (config / "user.toml").write_bytes(b"user-only file")
    (inputs["config"] / "new.toml").write_bytes(b"new default")
    assert regress.main(cli) == 0
    assert (config / "global.toml").read_bytes() == b"custom global"
    assert (config / "games" / "PPSA00000.toml").read_bytes() == b"custom per-title"
    assert (config / "user.toml").read_bytes() == b"user-only file"
    assert (config / "new.toml").read_bytes() == b"new default"


def test_prepare_explicit_config_and_intel_flag(prepared_inputs, tmp_path):
    inputs = prepared_inputs
    config = tmp_path / "custom config"
    config.mkdir()
    (config / "global.toml").write_text("schema=1\n[display]\nfullscreen=true\n")
    assert regress.main(prepare_cli(inputs, config=config, **{"to-intel": True})) == 0
    assert inputs["calls"][0][0][1:3] == ["--windows", "--to-intel"]
    assert not (inputs["install"] / "config" / "games").exists()
    assert (inputs["install"] / "config" / "global.toml").read_bytes() == (
        config / "global.toml"
    ).read_bytes()


@pytest.mark.parametrize("name", regress.REQUIRED_RUNTIME_FILES)
def test_prepare_requires_each_runtime_dependency(prepared_inputs, capsys, name):
    (prepared_inputs["libs"] / name).unlink()
    assert name in assert_preflight_failure(prepared_inputs, capsys)


@pytest.mark.parametrize("field", ["dump", "libs", "relinker", "config"])
def test_prepare_missing_input_fails_before_writes(prepared_inputs, capsys, tmp_path, field):
    assert_preflight_failure(prepared_inputs, capsys, **{field: tmp_path / "missing"})


@pytest.mark.parametrize(
    "metadata",
    [
        None,
        [],
        {},
        {"titleId": "../bad"},
        {**METADATA, "titleId": "ppsa00000"},
        {**METADATA, "titleId": 123},
        {**METADATA, "localizedParameters": {}},
        {**METADATA, "defaultLanguage": None},
        {**METADATA, "localizedParameters": {"en-US": {"titleName": ""}}},
        {**METADATA, "localizedParameters": {"en-US": "invalid"}},
    ],
)
def test_prepare_rejects_metadata_runtime_cannot_use(prepared_inputs, capsys, metadata):
    path = prepared_inputs["dump"] / "sce_sys" / "param.json"
    path.write_text(json.dumps(metadata), encoding="utf-8")
    assert "param.json" in assert_preflight_failure(prepared_inputs, capsys)


@pytest.mark.parametrize("content", [b"not-json private fixture", b"\xff"])
def test_prepare_metadata_errors_do_not_expose_contents(prepared_inputs, capsys, content):
    path = prepared_inputs["dump"] / "sce_sys" / "param.json"
    path.write_bytes(content)
    error = assert_preflight_failure(prepared_inputs, capsys)
    assert "private fixture" not in error and "Traceback" not in error


@pytest.mark.parametrize(
    "metadata",
    [
        {
            **METADATA,
            "defaultLanguage": "fr-FR",
            "localizedParameters": {
                "fr-FR": {"titleName": "Synthetic"},
                "en-US": {"titleName": ""},
            },
        },
        {**METADATA, "defaultLanguage": "missing"},
        {"titleId": "SYNTHETIC1", "localizedParameters": {"fr-FR": {"titleName": "Synthetic"}}},
    ],
)
def test_prepare_metadata_uses_runtime_language_fallback(prepared_inputs, metadata):
    (prepared_inputs["dump"] / "sce_sys" / "param.json").write_text(json.dumps(metadata))
    assert regress.main(prepare_cli(prepared_inputs)) == 0


@pytest.mark.parametrize("source", ["dump", "libs", "config"])
@pytest.mark.parametrize("position", ["equal", "child", "parent"])
def test_prepare_rejects_install_source_overlap(prepared_inputs, capsys, source, position):
    path = prepared_inputs[source]
    install = path if position == "equal" else path / "out" if position == "child" else path.parent
    assert regress.main(prepare_cli(prepared_inputs, install=install)) == 1
    assert prepared_inputs["calls"] == []
    assert "overlap" in capsys.readouterr().err or source == "config"


def test_prepare_rejects_install_junction_alias_of_dump(prepared_inputs, capsys):
    inputs = prepared_inputs
    directory_link(inputs["install"], inputs["dump"])
    assert regress.main(prepare_cli(inputs)) == 1
    assert inputs["calls"] == []
    assert "overlap" in capsys.readouterr().err
    assert not (inputs["dump"] / "game.exe").exists()


@pytest.mark.parametrize("kind", ["directory", "wrong_link", "broken_link"])
def test_prepare_rejects_stale_or_nonlink_app0_before_conversion(
    prepared_inputs, capsys, tmp_path, kind
):
    inputs = prepared_inputs
    inputs["install"].mkdir()
    app0 = inputs["install"] / "app0"
    target = tmp_path / "another dump"
    if kind == "directory":
        app0.mkdir()
    else:
        target.mkdir()
        directory_link(app0, target)
        if kind == "broken_link":
            target.rmdir()
    assert regress.main(prepare_cli(inputs)) == 1
    assert inputs["calls"] == []
    assert "app0" in capsys.readouterr().err


@pytest.mark.parametrize("name", ["libs", "config", "sce_module"])
def test_prepare_rejects_output_junctions_before_writing(prepared_inputs, capsys, tmp_path, name):
    inputs = prepared_inputs
    inputs["install"].mkdir()
    outside = tmp_path / "other"
    outside.mkdir()
    directory_link(inputs["install"] / name, outside)
    assert regress.main(prepare_cli(inputs)) == 1
    assert inputs["calls"] == []
    assert "links" in capsys.readouterr().err
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("source", ["libs", "config"])
def test_prepare_rejects_source_junctions(prepared_inputs, capsys, source):
    directory_link(prepared_inputs[source] / "nested", prepared_inputs["dump"])
    assert "links" in assert_preflight_failure(prepared_inputs, capsys)


def test_prepare_rejects_hardlinked_output(prepared_inputs, capsys):
    inputs = prepared_inputs
    inputs["install"].mkdir()
    (inputs["install"] / "game.exe").hardlink_to(inputs["dump"] / "eboot.elf")
    assert regress.main(prepare_cli(inputs)) == 1
    assert inputs["calls"] == []
    assert "unlinked" in capsys.readouterr().err
    assert (inputs["dump"] / "eboot.elf").read_bytes() == b"synthetic"


def test_prepare_detects_config_file_directory_collision(prepared_inputs, capsys):
    inputs = prepared_inputs
    (inputs["install"] / "config").mkdir(parents=True)
    (inputs["install"] / "config" / "games").write_bytes(b"existing customization")
    assert regress.main(prepare_cli(inputs)) == 1
    assert inputs["calls"] == []
    assert "conflict" in capsys.readouterr().err


def test_prepare_reports_failed_conversion_without_tool_output(
    prepared_inputs, monkeypatch, capsys
):
    inputs = prepared_inputs

    def fail(command, **kwargs):
        """Model a relinker failure with private output that must stay suppressed."""
        assert kwargs["stderr"] == kwargs["stdout"] == subprocess.DEVNULL
        raise subprocess.CalledProcessError(2, command, output="private fixture")

    monkeypatch.setattr(regress.subprocess, "run", fail)
    assert regress.main(prepare_cli(inputs)) == 1
    error = capsys.readouterr().err
    assert "exit code 2" in error and "private fixture" not in error
    assert not (inputs["install"] / "config").exists()
    assert not (inputs["install"] / "libs").exists()
