# Phase 5 — Production hardening

Phase 5 hardens Aivatar for long-running local production without changing the provider architecture established in Phases 1–4.

## Added

- Durable job heartbeats, retry limits, cancellation, manual retry, and restart re-queue for eligible interrupted jobs.
- Project operator leases to prevent conflicting timeline edits when a shared local database is used.
- Workspace usage reporting and explicit cleanup for render/cache intermediates.
- LRU-style generated-asset cache pruning by age or byte budget.
- Production run metrics for wall time, retries, storage, measured/estimated spend, and cost per finished minute.
- Sampled final QC for effectively silent audio and obvious black-frame failures.
- Long-form assembly stress harness for 5, 10, and 30–40 minute validation without pretending it measures diffusion throughput.
- Three-project concurrency stress harness independent from image/video/presenter resource semaphores.
- macOS packaging scripts that build the Python API as a PyInstaller sidecar and bundle it with Tauri.

## macOS packaging

Run `scripts/bootstrap_macos.sh`, then `scripts/build_macos_app.sh` on a Mac with Xcode Command Line Tools installed. The build script creates the architecture-specific `aivatar-api` sidecar and asks Tauri for `.app` and `.dmg` bundles.

Signing/notarization credentials are intentionally not committed. Production distribution should provide Apple signing/notarization credentials through the build environment.

## Long-form proof scope

The Phase-5 30-minute proof uses stream-copy assembly of a valid one-minute 1080p seed. It validates duration handling, container assembly, audio/subtitle presence, checksum/QC, and long-duration manifests. It does **not** claim that FLUX/LTX/HeyGen can generate 30 minutes at the same wall-clock speed.

Live provider cost targets remain unproven until authorized AI33/HeyGen/RunPod/R2 credentials are exercised end-to-end.
