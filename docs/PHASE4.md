# Phase 4 — Visual Optimization and GPU Scheduling

Phase 4 turns Aivatar's visual generation layer into a budget-aware, cache-first system instead of treating every B-roll scene as an independent diffusion job.

## Decision order

For each visual scene, the Director now evaluates:

1. an existing content-addressed cache entry;
2. a template-driven motion graphic when the scene is primarily a title/callout/keyword/statistic;
3. LTX 2.3 only when the prompt's motion value is high enough, the scene is short enough, the LTX scene cap has not been reached, and visual budget remains;
4. otherwise a FLUX.2 Klein still plus local FFmpeg motion.

The cost values used during planning are estimates only. Production `CostEntry` records remain the source of truth for measured provider/GPU spend.

## LTX 2.3 worker

The RunPod Serverless worker follows the current official Lightricks LTX-2 pipeline structure:

- checkpoint: `ltx-2.3-22b-distilled-1.1.safetensors`
- spatial upscaler: `ltx-2.3-spatial-upscaler-x2-1.1.safetensors`
- text encoder: `google/gemma-3-12b-it-qat-q4_0-unquantized`
- pipeline: `ltx_pipelines.distilled`
- default quantization: `none` for the proven A100 profile; optional quantization is configurable per deployment
- dimensions are snapped to multiples of 32
- frame count is snapped to the LTX `8k+1` rule
- any LTX-generated audio is stripped before persistence because Aivatar's master narration is authoritative

The Docker image clones the official `Lightricks/LTX-2` source. For production deployment, set `LTX_REF` to a reviewed commit SHA rather than relying on `main`.

## Shared asset cache

`workspace/cache/assets/` is content-addressed by:

- asset type
- provider
- model
- normalized prompt
- generation parameters

Identical jobs can be reused across projects. Cache hits are explicitly recorded as zero-generation-cost events and copied/hard-linked into a project without rerunning the model.

## Motion graphics

Phase 4 adds cheap FFmpeg templates for:

- section headers
- callouts
- highlighted keywords
- lower thirds

The system can render these over still/video scenes without an AI-video call.

## GPU scheduling

RunPod endpoint metadata now participates in provider selection. The scheduler checks:

- capability (`image`, `video`, `presenter`)
- minimum VRAM
- configured endpoint
- known hourly planning price

The A100 80 GB profile is retained as the proven benchmark, not as a hardcoded production requirement. GPU profiles remain configurable.

## Concurrency

The queue uses shared resource semaphores for:

- project jobs
- image GPU jobs
- video GPU jobs
- presenter jobs
- FFmpeg jobs

This prevents asset-level work from silently bypassing the application's resource controls.

## Phase-4 proof

`scripts/render_phase4_mock_project.py` creates a 60-second 1080p project that exercises the real optimization/cache/render code while using mock model providers when live GPU credentials are unavailable.

The proof deliberately contains:

- 30% presenter visibility
- presenter-only scene
- template motion graphics
- selective LTX decisions
- a cross-project/shared cache hit
- SPLIT and PIP presenter composition
- master narration and captions
- resumable scene intermediates
- final FFmpeg QC

A mock proof has zero external API spend by definition. It does **not** prove the final $3–$5 production cost target; that requires live end-to-end measurement in Phase 5.
