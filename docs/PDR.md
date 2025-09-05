# Problem Definition & Rationale (PDR): Deterministic Change Planning

## Problem
Change proposals were implicit in ad-hoc CLI output and diffs scattered across folders. This made it hard to:
- Review planned changes in PRs
- Reproduce plans deterministically for audit
- Archive a single portable artifact in CI

## Goals
- Generate a self-contained, deterministic plan describing:
  - Device, intent, exact commands, unified diff
  - Inputs and their SHA256 hashes
  - Rollback steps and post-change verification summary
  - Provenance: tool version and git revision
- Provide Markdown (human) and JSON (machine) outputs
- Avoid timestamps; use content and git hashes

## Non-Goals
- Live device interaction changes. Existing live-mode flow remains.
- Complex rollback orchestration; we document safe guidance.

## Design Overview
- Extend `scripts.push_change` with `--plan-out` and `--plan-json`.
- Reuse existing offline transforms to compute after-config and diff.
- Build a deterministic plan dict, then render:
  - `plan.md`: stable section order and content
  - `plan.json`: stable key order via `sort_keys=True`
- Compute file/text SHA256 and include repo git revision.
- CI uploads the artifacts for every run.

## Risks and Mitigations
- Risk: YAML/Markdown non-determinism. Mitigation: sorted keys/sections and avoid timestamps.
- Risk: Missing after-config on disk. Mitigation: hash in-memory text when not written.

## Test Strategy
- Unit tests for rendering helpers and hashing.
- Golden snapshots for `plan.md`/`plan.json` in offline demo.
- CI smoke: generate plans and upload as artifacts.

## Rollout
- Backward compatible flags. Default behavior unchanged.
- Docs updated; CI includes artifacts.