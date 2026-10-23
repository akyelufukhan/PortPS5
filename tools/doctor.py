#!/usr/bin/env python3
"""Read-only developer prerequisite checks for PortPS5's Windows build.

This stdlib-only CLI inspects the current process, tools on PATH and local
submodule initialization markers. It installs nothing and makes no network
requests. Checks run sequentially with bounded subprocess waits; no persistent
state or game data is read. Passing does not establish build, GPU or game
compatibility, or verify submodule revisions against the recorded Git pins.
"""

import argparse
import configparser
import json
import platform
import re
import shutil
import struct
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PROBE_TIMEOUT = 5
COMPILER_REMEDY = (
    "Use the pinned winlibs MinGW-w64 GCC 15.2.0 x86_64-ucrt-posix-seh toolchain "
    "and put its bin directory first on PATH. See docs/spec/build-toolchain.md."
)
SUBMODULE_REMEDY = "From the repository root, run: git submodule update --init --recursive"
SCOPE_NOTE = (
    "Checks cover development prerequisites only. Build success, GPU/game compatibility "
    "and submodule revision pins are not verified."
)


@dataclass(frozen=True)
class Check:
    """One stable report row; passing checks have no suggested remedy."""

    id: str
    status: str
    message: str
    remedy: str | None = None


def probe(arguments: list[str]) -> tuple[str | None, str | None]:
    """Run a version query without a shell; return stdout or a sanitized error.

    Tool output and exception text are never echoed on failure because wrappers
    can include unrelated local paths or environment values in diagnostics.
    """
    try:
        result = subprocess.run(
            arguments,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PROBE_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, f"query timed out after {PROBE_TIMEOUT} seconds"
    except OSError:
        return None, "could not execute the tool"
    if result.returncode != 0:
        return None, f"query exited with code {result.returncode}"
    return result.stdout.strip(), None


def check_host() -> Check:
    """Require Windows x64 and a 64-bit interpreter for the native build."""
    system, machine = platform.system(), platform.machine()
    bits = struct.calcsize("P") * 8
    if system == "Windows" and machine.lower() in ("amd64", "x86_64") and bits == 64:
        return Check("host", "pass", "Windows x64 with 64-bit Python")
    return Check(
        "host",
        "fail",
        "The supported native build requires Windows x64 and 64-bit Python.",
        "Run this check on Windows x64 using a 64-bit Python interpreter.",
    )


def check_python() -> Check:
    """Check the running interpreter rather than a potentially different PATH Python."""
    version = tuple(sys.version_info[:3])
    label = ".".join(map(str, version))
    if version >= (3, 11, 0):
        return Check("python", "pass", f"Python {label}")
    return Check(
        "python", "fail", f"Python {label}; need >=3.11.", "Run with Python 3.11 or newer."
    )


def check_version(
    name: str,
    pattern: str,
    remedy: str,
    minimum: tuple[int, int, int] | None = None,
) -> Check:
    """Check a PATH tool's recognizable version and an optional minimum."""
    executable = shutil.which(name)
    if executable is None:
        return Check(name, "fail", f"{name} was not found on PATH.", remedy)
    output, error = probe([executable, "--version"])
    if error:
        return Check(name, "fail", f"{name}: {error}.", remedy)
    match = re.match(pattern, output or "")
    if match is None:
        return Check(name, "fail", f"{name}: unrecognized version response.", remedy)
    label = match.group(1)
    parts = tuple(int(part) for part in label.split("."))
    version = (*parts, 0, 0, 0)[:3]
    if minimum and version < minimum:
        required = ".".join(map(str, minimum))
        return Check(name, "fail", f"{name} {label}; need >={required}.", remedy)
    return Check(name, "pass", f"{name} {label}")


def check_compiler() -> Check:
    """Match the CMake compiler search order, exact GCC version and target triple."""
    executable = shutil.which("g++") or shutil.which("x86_64-w64-mingw32-g++")
    if executable is None:
        return Check("compiler", "fail", "MinGW g++ was not found on PATH.", COMPILER_REMEDY)
    version, error = probe([executable, "-dumpfullversion", "-dumpversion"])
    if error:
        return Check("compiler", "fail", f"g++: {error}.", COMPILER_REMEDY)
    if not re.fullmatch(r"\d+\.\d+\.\d+", version or ""):
        return Check("compiler", "fail", "g++: unrecognized version response.", COMPILER_REMEDY)
    if version != "15.2.0":
        return Check("compiler", "fail", f"GCC {version}; need exactly 15.2.0.", COMPILER_REMEDY)
    target, error = probe([executable, "-dumpmachine"])
    if error:
        return Check("compiler", "fail", f"g++ target: {error}.", COMPILER_REMEDY)
    if target != "x86_64-w64-mingw32":
        return Check(
            "compiler",
            "fail",
            "g++ target is not x86_64-w64-mingw32.",
            COMPILER_REMEDY,
        )
    return Check("compiler", "pass", "GCC 15.2.0 targeting x86_64-w64-mingw32")


def check_submodules(root: Path) -> list[Check]:
    """Read the manifest and check initialization markers without invoking Git.

    A directory alone is insufficient: an uninitialized checkout may already
    contain an empty submodule directory. Accept Git's .git file or directory;
    pin/revision verification remains the configure/build workflow's job.
    """
    parser = configparser.ConfigParser(interpolation=None)
    manifest_remedy = "Restore .gitmodules from the repository before checking submodules."
    try:
        parser.read_string((root / ".gitmodules").read_text(encoding="utf-8"))
        paths = [parser.get(section, "path") for section in parser.sections()]
        if not paths or len(paths) != len(set(paths)):
            raise ValueError("empty or duplicate submodule paths")
        for path in paths:
            # Do not inspect a path outside the checkout, including symlink escapes.
            if (
                not path
                or "\\" in path
                or ":" in path
                or PurePosixPath(path).is_absolute()
                or any(part in ("", ".", "..") for part in path.split("/"))
                or not (root / path).resolve().is_relative_to(root.resolve())
            ):
                raise ValueError("invalid submodule path")
    except (OSError, UnicodeError, configparser.Error, ValueError):
        return [Check("submodules", "fail", ".gitmodules is missing or invalid.", manifest_remedy)]
    checks = []
    for path in sorted(paths):
        marker = root / path / ".git"
        initialized = marker.is_file() or marker.is_dir()
        checks.append(
            Check(
                f"submodule:{path}",
                "pass" if initialized else "fail",
                f"{path}: initialization marker {'present' if initialized else 'missing'}.",
                None if initialized else SUBMODULE_REMEDY,
            )
        )
    return checks


def collect_checks(root: Path) -> list[Check]:
    """Collect checks in a stable order without short-circuiting on blockers."""
    return [
        check_host(),
        check_python(),
        check_version(
            "git", r"git version (\d+\.\d+(?:\.\d+)?)\b", "Install Git and add it to PATH."
        ),
        check_version(
            "cmake",
            r"cmake version (\d+\.\d+\.\d+)\b",
            "Install CMake >=3.25 and add it to PATH.",
            (3, 25, 0),
        ),
        check_version("ninja", r"(\d+\.\d+(?:\.\d+)?)\b", "Install Ninja and add it to PATH."),
        check_compiler(),
        *check_submodules(root),
    ]


def main(argv: list[str] | None = None) -> int:
    """Print text or schema-versioned JSON; return 1 when any prerequisite fails."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit a machine-readable JSON report")
    arguments = parser.parse_args(argv)
    checks = collect_checks(ROOT)
    ready = all(check.status == "pass" for check in checks)
    if arguments.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ready": ready,
                    "checks": [asdict(check) for check in checks],
                },
                indent=2,
            )
        )
    else:
        print("PortPS5 developer preflight")
        for check in checks:
            print(f"[{check.status.upper()}] {check.message}")
            if check.remedy:
                print(f"  Fix: {check.remedy}")
        blockers = sum(check.status == "fail" for check in checks)
        print(f"\n{blockers} blocking check(s). {SCOPE_NOTE}")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
