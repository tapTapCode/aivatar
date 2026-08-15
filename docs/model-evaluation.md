# Model Evaluation

All candidate execution results are `NOT TESTED` on this host.

## Candidate matrix

| Stage | Candidate | Verified public fact | Required local evaluation |
| --- | --- | --- | --- |
| Image | FLUX.2 [klein] 4B | The [official repository](https://github.com/black-forest-labs/flux2) lists 4B distilled/base variants and Apache-2.0 licensing for 4B. | Pin revision; bf16/FP8/NVFP4; latency, VRAM, prompt adherence, identity, text. |
| Video | LTX-2.3 22B + distilled LoRA v1.1 | [Official LTX docs](https://docs.ltx.io/open-source-model/usage-guides/text-to-video) describe an 8-step low-resolution stage, spatial upscale, and 3-step refinement, and link a Python API. | Official Python pipeline; exact checkpoint/LoRA; offload, decoding, artifacts, 32 GB feasibility. |
| Voice | Chatterbox | Candidate only in this project. | License review, pinned executable distribution, naturalness, pacing, consent, long-form stability. |
| Lip sync | MuseTalk 1.5 | The [official repository](https://github.com/TMElyralab/MuseTalk) publishes 1.5 inference/training code and documents Python 3.10/CUDA 11.7. | Blackwell-compatible environment, face pipeline, identity, teeth, flicker, sync, full-frame quality. |

No candidate is attributed to FaceTuber.

## Image protocol

Use fixed prompts and seeds across native bf16, officially supported FP8/NVFP4, distilled, and base
checkpoints. Record cold load, prompt encode, denoise, decode, encode, end-to-end, peak allocated,
peak reserved, and NVML device memory. Human review covers prompt adherence, identity consistency,
text failures, and defects. Official vendor performance statements are not project measurements.

## Video protocol

Record generation mode, resolution, frames, FPS, exact step schedule, seed, audio mode, upscalers,
precision, quantization, and offload. Separate text encoding, latent preparation, both denoising
stages, spatial/temporal upscaling, decode, encode, and upload. Inspect temporal consistency,
artifact frequency, and final-frame instability. Do not state 32 GB fit without measurement.

## Voice and lip-sync protocol

Voice WAV is normalized before encoding. Tests require documented voice permission, multiple pacing
conditions, sentence timing, pronunciation cases, clipping and loudness inspection. MuseTalk uses a
fixed 10-second source clip/audio fixture plus close/medium framing, poses, lighting, slow/fast
speech, plosives, closures, long narration, and scene cuts. Lip-region metrics supplement full-frame
blind review; they do not establish HeyGen parity.

## Adapter acceptance

An adapter is accepted only when it returns full `GeneratedAsset` provenance, uses a pinned model
revision, produces content-hash-verified media, passes media validation, and exposes actual stage
times and CUDA/NVML memory. Workers remain unready until `MODEL_ADAPTER=module:factory` is supplied.

