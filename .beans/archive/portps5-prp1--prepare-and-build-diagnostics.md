---
# portps5-prp1
title: 'Complete preparation defaults and add build diagnostics'
status: completed
type: feature
priority: high
created_at: 2026-10-23T19:17:29Z
parent: portps5-r8mh
---

## Context

The preparation command omits config files and can finish without runtime libraries. New contributors discover missing build prerequisites during CMake configuration. Blocked by: none. Reviewed PortPS5 `aa7d6da` and AnyPS5 `d7948b0`; the latter has no equivalent `tools/regress.py` workflow. These changes are implemented for this fork without copying upstream code. The beans CLI is unavailable locally, so this task uses its documented Markdown format directly.

## Higher Goal

Make the Windows preparation workflow predictable while preserving user configuration, source dumps, and the existing clean-room boundary. Keep the published fork's changes distinct from inherited runtime capabilities.

## Acceptance Criteria

- [x] Preparation copies missing config files and preserves existing files.
- [x] Preparation checks inputs and destination conflicts before conversion.
- [x] Intel lowering is selectable through `prepare --to-intel`.
- [x] A read-only doctor command reports build blockers in text and JSON.
- [x] CMake minimum version matches the presets schema.
- [x] Synthetic preparation and doctor tests pass; Python lint and formatting pass.
- [x] User guide, subsystem specs, roadmap and fork notes describe the delivered behavior.

## Out of Scope

Runtime telemetry wiring, GPU changes, additional game compatibility claims, game dumps, and binary releases.

## Summary of Changes

Delivered preparation config seeding, runtime/path validation, Intel forwarding, read-only doctor, CMake minimum alignment, Windows/Linux Python CI and fork documentation. Local verification: 302 passed, 3 POSIX-only tests skipped on Windows, 2 subtests passed; 88.90% tools coverage; Ruff lint/format passed. Presets parsed with CMake 3.25.2. Native C++ compilation and real-game runs were not performed locally.

Hosted verification of `3475099` passed in [CI](https://github.com/akyelufukhan/PortPS5/actions/runs/40012076506): full MinGW C++ build, unit and golden shader tests, policy checks, 58 lavapipe tests and both Python jobs (Windows 302 passed/3 skipped, Linux 305 passed). CodeQL, Gitleaks and Doxygen also passed. No real-game run was performed.
