"""Hermetic developer preflight tests using synthetic tools and submodules.

No test depends on the host toolchain, downloads software or executes a tool
from PATH. Each fixture isolates filesystem and process state with pytest.
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import doctor


@pytest.fixture
def ready_environment(tmp_path, monkeypatch):
    """Provide a Windows x64 toolchain and a locally initialized synthetic module."""
    monkeypatch.setattr(doctor, "ROOT", tmp_path)
    monkeypatch.setattr(doctor.platform, "system", lambda: "Windows")
    monkeypatch.setattr(doctor.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(doctor.struct, "calcsize", lambda _format: 8)
    monkeypatch.setattr(doctor.sys, "version_info", (3, 11, 0))
    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/synthetic tools/{name}")
    (tmp_path / ".gitmodules").write_text(
        '[submodule "dependency"]\n\tpath = 3rdparty/dependency\n', encoding="utf-8"
    )
    dependency = tmp_path / "3rdparty" / "dependency"
    dependency.mkdir(parents=True)
    (dependency / ".git").write_text("gitdir: synthetic", encoding="utf-8")
    responses = {
        "git": "git version 2.50.1.windows.1\n",
        "cmake": "cmake version 3.25.0\n\nCMake suite maintained by Kitware.",
        "ninja": "1.12.1\n",
        "-dumpversion": "15.2.0\n",
        "-dumpmachine": "x86_64-w64-mingw32\n",
    }

    def run(arguments, **kwargs):
        """Return only supported query results, enforcing safe process invocation."""
        assert isinstance(arguments, list)
        assert kwargs == {
            "capture_output": True,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "timeout": 5,
            "check": False,
        }
        key = Path(arguments[0]).name if arguments[-1] == "--version" else arguments[-1]
        return subprocess.CompletedProcess(arguments, 0, stdout=responses[key], stderr="")

    runner = Mock(side_effect=run)
    monkeypatch.setattr(doctor.subprocess, "run", runner)
    return tmp_path, responses, runner


def test_json_cli_passes_with_stable_schema(ready_environment, capsys):
    assert doctor.main(["--json"]) == 0
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert output.err == ""
    assert set(report) == {"schema_version", "ready", "checks"}
    assert report["schema_version"] == 1
    assert report["ready"] is True
    assert [check["id"] for check in report["checks"]] == [
        "host",
        "python",
        "git",
        "cmake",
        "ninja",
        "compiler",
        "submodule:3rdparty/dependency",
    ]
    assert all(check["status"] == "pass" for check in report["checks"])
    assert all(check["remedy"] is None for check in report["checks"])
    assert all(set(check) == {"id", "status", "message", "remedy"} for check in report["checks"])
    assert "/synthetic tools" not in output.out


@pytest.mark.parametrize(
    ("system", "machine", "pointer_bytes"),
    [("Linux", "x86_64", 8), ("Windows", "ARM64", 8), ("Windows", "AMD64", 4)],
)
def test_unsupported_host_is_a_blocker(
    ready_environment, monkeypatch, system, machine, pointer_bytes
):
    monkeypatch.setattr(doctor.platform, "system", lambda: system)
    monkeypatch.setattr(doctor.platform, "machine", lambda: machine)
    monkeypatch.setattr(doctor.struct, "calcsize", lambda _format: pointer_bytes)
    assert doctor.check_host().status == "fail"


@pytest.mark.parametrize("machine", ["AMD64", "amd64", "x86_64"])
def test_supported_host_aliases(ready_environment, monkeypatch, machine):
    monkeypatch.setattr(doctor.platform, "machine", lambda: machine)
    assert doctor.check_host().status == "pass"


@pytest.mark.parametrize(
    ("version", "status"), [((3, 10, 9), "fail"), ((3, 11, 0), "pass"), ((3, 12, 1), "pass")]
)
def test_running_python_version(ready_environment, monkeypatch, version, status):
    monkeypatch.setattr(doctor.sys, "version_info", version)
    assert doctor.check_python().status == status


@pytest.mark.parametrize("tool", ["git", "cmake", "ninja", "g++"])
def test_missing_tools_fail_without_launching_them(ready_environment, monkeypatch, tool):
    root, _, runner = ready_environment
    monkeypatch.setattr(
        doctor.shutil,
        "which",
        lambda name: None if name in (tool, "x86_64-w64-mingw32-g++") else name,
    )
    checks = doctor.collect_checks(root)
    expected_id = "compiler" if tool == "g++" else tool
    assert next(check for check in checks if check.id == expected_id).status == "fail"
    assert all(call.args[0][0] != tool for call in runner.call_args_list)


@pytest.mark.parametrize(
    ("version", "status"), [("3.24.9", "fail"), ("3.25.0", "pass"), ("4.1.0", "pass")]
)
def test_cmake_minimum_version(ready_environment, version, status):
    root, responses, _ = ready_environment
    responses["cmake"] = f"cmake version {version}"
    check = next(check for check in doctor.collect_checks(root) if check.id == "cmake")
    assert check.status == status


@pytest.mark.parametrize("tool", ["git", "cmake", "ninja", "-dumpversion", "-dumpmachine"])
@pytest.mark.parametrize("output", ["", "garbage SECRET_VALUE", "version unavailable"])
def test_malformed_tool_output_is_sanitized(ready_environment, tool, output):
    root, responses, _ = ready_environment
    responses[tool] = output
    failed = [check for check in doctor.collect_checks(root) if check.status == "fail"]
    assert len(failed) == 1
    assert failed[0].remedy
    assert "SECRET_VALUE" not in failed[0].message


@pytest.mark.parametrize("version", ["14.2.0", "15.1.0", "15.2.1", "16.0.0"])
def test_compiler_is_pinned_exactly(ready_environment, version):
    _, responses, _ = ready_environment
    responses["-dumpversion"] = version
    check = doctor.check_compiler()
    assert check.status == "fail"
    assert "exactly 15.2.0" in check.message


@pytest.mark.parametrize("target", ["x86_64-linux-gnu", "i686-w64-mingw32", "aarch64-w64-mingw32"])
def test_compiler_wrong_target_fails(ready_environment, target):
    _, responses, _ = ready_environment
    responses["-dumpmachine"] = target
    assert doctor.check_compiler().status == "fail"


def test_prefixed_compiler_fallback(ready_environment, monkeypatch):
    _, _, runner = ready_environment
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None if name == "g++" else name)
    assert doctor.check_compiler().status == "pass"
    assert runner.call_args_list[0].args[0][0] == "x86_64-w64-mingw32-g++"


@pytest.mark.parametrize(
    "failure",
    [subprocess.TimeoutExpired("tool", 5, output="SECRET_VALUE"), OSError("SECRET_VALUE")],
)
def test_probe_errors_are_actionable_and_sanitized(ready_environment, failure):
    root, _, runner = ready_environment
    runner.side_effect = failure
    checks = doctor.collect_checks(root)
    failed = [check for check in checks if check.status == "fail"]
    assert {check.id for check in failed} == {"git", "cmake", "ninja", "compiler"}
    assert all(check.remedy and "SECRET_VALUE" not in check.message for check in failed)


def test_nonzero_probe_exit_discards_both_output_streams(ready_environment):
    _, _, runner = ready_environment
    runner.side_effect = None
    runner.return_value = subprocess.CompletedProcess([], 7, "SECRET_VALUE", "SECRET_VALUE")
    assert doctor.probe(["tool", "--version"]) == (None, "query exited with code 7")


def test_compiler_target_probe_can_timeout(ready_environment):
    _, _, runner = ready_environment
    runner.side_effect = [
        subprocess.CompletedProcess([], 0, "15.2.0", ""),
        subprocess.TimeoutExpired("tool", 5),
    ]
    check = doctor.check_compiler()
    assert check.status == "fail"
    assert "target: query timed out" in check.message


def test_uninitialized_module_directory_fails(ready_environment):
    root, _, _ = ready_environment
    (root / "3rdparty/dependency/.git").unlink()
    check = doctor.check_submodules(root)[0]
    assert check.status == "fail"
    assert "git submodule update --init --recursive" in check.remedy


def test_older_git_directory_markers_are_supported(ready_environment):
    root, _, _ = ready_environment
    marker = root / "3rdparty/dependency/.git"
    marker.unlink()
    marker.mkdir()
    assert doctor.check_submodules(root)[0].status == "pass"


@pytest.mark.parametrize(
    "manifest",
    [
        "",
        "not an ini file",
        '[submodule "a"]\nurl = https://example.test/a',
        '[submodule "a"]\npath = ../outside',
        '[submodule "a"]\npath = /outside',
        '[submodule "a"]\npath = C:/outside',
        '[submodule "a"]\npath = ..\\outside',
        '[submodule "a"]\npath = .',
        '[submodule "a"]\npath = a//b',
        '[submodule "a"]\npath = a\n[submodule "b"]\npath = a',
    ],
)
def test_invalid_submodule_manifest_is_one_blocker(tmp_path, manifest):
    (tmp_path / ".gitmodules").write_text(manifest, encoding="utf-8")
    checks = doctor.check_submodules(tmp_path)
    assert len(checks) == 1
    assert checks[0].id == "submodules"
    assert checks[0].status == "fail"


def test_missing_or_unreadable_manifest_is_a_blocker(tmp_path):
    assert doctor.check_submodules(tmp_path)[0].status == "fail"
    (tmp_path / ".gitmodules").mkdir()
    assert doctor.check_submodules(tmp_path)[0].status == "fail"


def test_submodule_rows_are_sorted_by_path(tmp_path):
    (tmp_path / ".gitmodules").write_text(
        '[submodule "z"]\npath = z\n[submodule "a"]\npath = a', encoding="utf-8"
    )
    assert [check.id for check in doctor.check_submodules(tmp_path)] == [
        "submodule:a",
        "submodule:z",
    ]


def test_json_cli_returns_failure_without_extra_text(ready_environment, monkeypatch, capsys):
    monkeypatch.setattr(doctor.shutil, "which", lambda _name: None)
    assert doctor.main(["--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["ready"] is False
    assert sum(check["status"] == "fail" for check in report["checks"]) == 4


def test_text_cli_includes_remedies_and_limits(ready_environment, monkeypatch, capsys):
    monkeypatch.setattr(doctor.shutil, "which", lambda _name: None)
    assert doctor.main([]) == 1
    text = capsys.readouterr().out
    assert "[FAIL]" in text and "[PASS]" in text
    assert "Fix: Install CMake >=3.25" in text
    assert "4 blocking check(s)" in text
    assert "GPU/game compatibility" in text


def test_help_is_read_only_and_does_not_probe_tools(ready_environment, capsys):
    _, _, runner = ready_environment
    with pytest.raises(SystemExit, match="0"):
        doctor.main(["--help"])
    assert "--json" in capsys.readouterr().out
    runner.assert_not_called()
