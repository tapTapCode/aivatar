# Phase 5 Build Report

## Implemented

- Restart-safe durable job recovery: heartbeat, retry limit, resume count, cancellation, manual retry, and automatic re-queue of eligible interrupted jobs.
- Operator project leases to prevent conflicting scene edits when a team shares one local database/workspace.
- Production run metrics for wall time, retries, storage bytes, estimated/actual spend, and cost per finished minute.
- Explicit local storage cleanup and generated-asset cache pruning.
- Sampled QC for effective silence and obvious black-frame failure in addition to stream/container/duration/resolution checks.
- 5/10/30-minute 1080p long-form assembly stress harness.
- Three simultaneous complete synthetic projects as an application-level concurrency proof.
- PyInstaller FastAPI sidecar packaging for macOS Tauri builds.
- Tauri `.app` / `.dmg` build scripts with external sidecar configuration.
- R2 retention guidance based on prefix-scoped Object Lifecycle rules.

## Validation performed

- 37/37 automated tests passed when run in explicit groups.
- Python `compileall` passed.
- Clean Alembic migration reached `0004_phase5_hardening` and verified all Phase-5 columns/tables.
- 5-minute 1920×1080 assembly proof passed QC.
- 10-minute 1920×1080 assembly proof passed QC.
- 30-minute 1920×1080 assembly proof passed QC.
- Three simultaneous 1-minute 1920×1080 projects all passed QC.

## Important scope limits

The long-form proof uses stream-copy assembly from a valid one-minute seed. It proves long-duration container/timeline/QC behavior and avoids wasting compute, but it does not measure FLUX/LTX/HeyGen generation throughput.

The execution environment used for this build is Linux and does not have Rust/Cargo, Apple signing identities, or macOS notarization tooling. Therefore the Tauri source and sidecar packaging path were statically validated here, but a signed/notarized `.app`/`.dmg` must be built on macOS/Apple-capable CI.

No live paid provider credentials were used. End-to-end real spend for AI33/69Labs, HeyGen, RunPod, and R2 remains to be measured; the $3–$5 per 30-minute video target is not yet proven.
