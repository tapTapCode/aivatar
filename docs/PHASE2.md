# Phase 2 implementation notes

## Master audio and alignment

Aivatar treats `master_voice.wav` as the clock for the project. `pipeline.audio.master` normalizes imported/provider audio and can cut timestamp-exact segments for presenter generation without creating a second narration clock.

`pipeline.alignment.timestamps` accepts provider word timestamps when present. When unavailable, a deterministic weighted-word fallback creates duration-correct timestamps so the entire pipeline remains usable offline and in mock mode. This fallback is not claimed to be phoneme-accurate forced alignment; it is a safe continuity mechanism until a verified alignment provider/model is selected.

## RunPod

The default GPU transport is queue-based RunPod Serverless. The controller supports async submit, status polling, cancellation, retry and health checks. Project concurrency remains independent from GPU asset concurrency.

The architecture can still use ordinary RunPod Pods for benchmarking/debugging, but Aivatar no longer assumes a long-lived Pod or persistent model volume is required for normal image jobs.

## R2

Generated media is persisted through Cloudflare R2's S3-compatible API. Object keys are project scoped:

`projects/{project_id}/{category}/{filename}`

The FLUX worker uploads directly to R2 and returns an object key instead of embedding image bytes in RunPod job responses.

## FLUX.2 Klein

Default: `black-forest-labs/FLUX.2-klein-4B`.

The checkpoint remains environment-configurable. The Base checkpoint can be selected for fine-tuning/custom research workflows without changing provider code.

Worker defaults:

- 1280×720 asset generation (FFmpeg can compose/upscale to 1080p final output)
- 4 inference steps
- guidance 1.0
- deterministic seed support
- bfloat16 CUDA
- direct R2 upload
- runtime/GPU/peak-VRAM metadata

## LTX

The LTX provider transport boundary is present, but real LTX worker implementation remains Phase 4 because video diffusion should be selective and its dependency/GPU profile should stay isolated from the inexpensive image path.

The current configurable default is `ltx-2.3-22b-distilled-1.1`; this is not hardcoded into Director behavior.

## Voice providers

The WhatsApp requirements identify AI33 Pro and 69Labs, but do not provide a stable public API schema. The Phase-2 adapter therefore supports authorized configurable HTTP endpoints and common raw-audio/audio-URL responses without inventing a provider-specific private endpoint.

Once official account documentation is available, the adapter can be narrowed to that exact schema with contract tests.
