# Development fork

This fork is maintained at https://github.com/akyelufukhan/PortPS5.
Its starting point is ymatrix1/PortPS5 commit
`aa7d6da4759b3e9d5da8c1e580bf7b3ec3739725`. PortPS5 derives from
[AnyPS5](https://github.com/boykopovar/AnyPS5); the original history, copyright
notices and GPL-2.0-only license remain in place.

## First contribution: preparation and diagnostics

- `tools/doctor.py` reports missing developer prerequisites in text or JSON.
- `tools/regress.py prepare` seeds missing config files, preserves user edits,
  validates runtime files/metadata/paths and accepts `--to-intel`.
- Windows junction handling rejects stale targets before conversion and treats
  shell metacharacters in paths as literal data.
- CMake 3.25 is the declared minimum, matching presets schema version 6.
- Python CI runs on Windows and Linux; synthetic tests require no game data.

`prepare --libs` is now required. Supply the complete patched runtime output,
including MinGW DLLs. `--config` selects defaults to seed, not an instruction to
overwrite an existing installation. Conversion and library refresh can modify
existing generated outputs; this is not a transactional installer. The `app0`
link does not make the source dump read-only.

## Verification and limits

Local Windows validation: 302 tests passed, 3 POSIX-only tests skipped, 2 subtests passed; tools coverage 88.90%. Ruff lint/format passed and CMake 3.25.2 parsed all presets.
No native C++ build or real-game execution has been performed locally for this
contribution. The native compiler and submodules are separate prerequisites;
the doctor command reports them explicitly. Existing compatibility reports
are inherited upstream reports, not new measurements by this fork.

Hosted verification of commit `3475099` passed in [GitHub Actions](https://github.com/akyelufukhan/PortPS5/actions/runs/40012076506):
the full MinGW GCC 15.2 C++ build, unit and golden shader tests, policy checks,
and all 58 Mesa lavapipe driver tests. Python CI passed on Windows (302 passed,
3 POSIX-only skips; 88.97% coverage) and Linux (305 passed; 89.99% coverage).
CodeQL, Gitleaks and the Doxygen gate also passed. These synthetic checks do
not establish real-game compatibility or performance.

Runtime telemetry integration, additional playable games, GPU improvements,
and binary releases remain separate work. See [ROADMAP.md](ROADMAP.md).

## Optional publishing

To publish progress charts, enable GitHub Pages with GitHub Actions as its
source, then set the repository variable `PORTPS5_PAGES_ENABLED` to `true`.
The optional Pages workflow skips otherwise. Normal CI does not require Pages.
