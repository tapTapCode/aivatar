# Aivatar GPU workers

GPU inference runs outside the desktop app. Production jobs use RunPod Serverless queue endpoints by default so image/video jobs can autoscale independently of the three-project application limit.

## FLUX.2 Klein worker

`workers/flux` is a real RunPod Serverless handler. It:

1. starts in an ephemeral container;
2. downloads `black-forest-labs/FLUX.2-klein-4B` from Hugging Face into the temporary worker cache;
3. generates an image with the official distilled-model defaults (4 steps, guidance 1.0 unless overridden);
4. uploads the PNG directly to Cloudflare R2;
5. returns only metadata/R2 key, including runtime, GPU model and peak allocated VRAM.

Required worker environment variables:

- `HF_TOKEN` when needed
- `R2_ACCOUNT_ID`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_BUCKET`
- optional `AIVATAR_FLUX_MODEL`

`musetalk` and `ltx` remain separate containers because their dependencies and GPU/resource profiles differ.

## LTX 2.3 worker

`workers/ltx` now implements a RunPod Serverless worker around Lightricks' official `LTX-2`/`ltx-pipelines` distilled path. It downloads the selected checkpoint, spatial upscaler and Gemma text encoder from Hugging Face inside the ephemeral worker, generates the clip, strips generated audio, uploads the silent MP4 to R2 and returns runtime/GPU metadata for the cost ledger.

The default A100 profile uses no FP8 quantization; `AIVATAR_LTX_QUANTIZATION` and `AIVATAR_LTX_OFFLOAD` remain deployment overrides. Set Docker build arg `LTX_REF` to a reviewed LTX-2 commit SHA for a pinned production image.
