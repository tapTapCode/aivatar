# Deployment Runbook

## Local control-plane and mock demonstration

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
python -m scripts.generate_demo --project examples/three-format-project.json
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

The demonstration uses colored mock media and a tone WAV. It verifies routing/composition/media
contracts only and is not an avatar, TTS, image, or video quality sample.

## Docker development

```bash
docker compose -f docker-compose.dev.yml build
docker compose -f docker-compose.dev.yml up
curl -fsS http://127.0.0.1:8001/ready
```

Docker execution is `NOT TESTED` on the development host used to create this repository.

## RTX 5090 host prerequisites

1. Install a Blackwell-compatible NVIDIA driver and NVIDIA Container Toolkit.
2. Verify `nvidia-smi` on host and inside the exact CUDA base image.
3. Enable BuildKit and provision persistent `/models` and `/data` volumes.
4. Pin image digests, source commits, checkpoint/LoRA revisions, and license approvals.
5. Build each worker separately. Do not copy one model environment into another.
6. Place only authorized avatar clips in `/data/avatars/{avatar_id}.mp4`, persist consent evidence,
   and include matching timezone-stamped consent records in requests.
7. Set `MODEL_ADAPTER=module:factory` per worker. The factory returns an object implementing the
   corresponding provider method and full provenance.
8. Set `PROVIDER_MODE=configured`; confirm `/ready` returns 200. An absent adapter must remain 503.
9. Start one heavyweight GPU worker at a time until peak memory and OOM recovery are verified.

```bash
docker compose -f docker-compose.gpu.yml build image-worker
docker compose -f docker-compose.gpu.yml up image-worker render-worker redis api
```

The Compose file reserves a GPU per model service. On a single-GPU workstation, use Compose
profiles/explicit service selection or an external scheduler; do not start all heavy models
concurrently.

## Single remote host

Keep API/Redis/PostgreSQL/object storage on a private network. Expose only the authenticated API.
Run one worker service bound to the RTX 5090 at a time or use a GPU lock. Persist model cache and
output storage. Health means process alive; readiness means dependencies, adapter, and model are
usable. Configure a supervisor restart on unrecoverable CUDA errors.

## Job/serverless GPU

Build immutable per-model images, pre-stage checkpoints in provider volumes/images where licensing
allows, submit a job with an asset URI and callback/queue ID, and record provider/region/rate date.
Cold startup, model download, model load, first CUDA, inference, encode, and upload must be separate
measurements. Never bake secrets into the image.

## Future multi-worker deployment

Use PostgreSQL for jobs/transitions/idempotency, Redis Streams or another acknowledged durable
queue, S3-compatible object storage, per-worker concurrency 1 for heavy models, OpenTelemetry,
Prometheus/DCGM, and a scheduler aware of GPU model residency. Add leases, heartbeats, dead-letter
handling, stage resume, and abandoned-temp cleanup before horizontal scaling.

## Troubleshooting

- Worker `/ready` 503: missing/unimportable adapter or unpinned model configuration.
- CUDA OOM: capture allocated/reserved/NVML data, stop co-resident models, retry once with the
  tested offload/quantization profile, then restart worker if CUDA is unhealthy.
- FFmpeg failure: retain command/stderr, verify source streams, libx264/libass, path permissions,
  dimensions, duration, and sample rate.
- A/V drift: inspect per-stream durations with ffprobe; ensure CFR, `setpts`/`asetpts`, normalized
  sample rate/channels, and scene-level duration tolerance.
- Cache mismatch: invalidate by full key/revision and verify source/content SHA-256.

Graceful shutdown should stop new dequeues, finish or checkpoint the current stage, extend/release
the lease, flush telemetry, unload models, and exit before the orchestrator timeout.
