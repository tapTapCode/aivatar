# Benchmark Methodology

## Prerequisites

- Actual NVIDIA GeForce RTX 5090 32 GB host (and separate A10G only for a measured comparison).
- NVIDIA driver, compatible CUDA/PyTorch, NVIDIA Container Toolkit, Docker BuildKit, NVML.
- Pinned Docker digests, source commits, model revisions, and quantization artifacts.
- Sufficient CPU RAM and local storage; storage type recorded.
- Authorized fixed avatar/voice fixtures; no background GPU jobs; stable thermal/power policy.
- Benchmark adapter factories that call official Python pipelines and return per-stage measurements.

## Command

```bash
python -m benchmarks.run \
  --device cuda:0 \
  --gpu-profile rtx5090 \
  --output-dir benchmark-results/rtx5090 \
  --cold-runs 5 \
  --warmup-runs 3 \
  --measured-runs 30 \
  --adapter image=deployment_benchmarks.flux:run \
  --adapter video=deployment_benchmarks.ltx:run \
  --adapter lipsync=deployment_benchmarks.musetalk:run
```

Without NVIDIA visibility or adapters, the command intentionally emits `NOT TESTED` reports and no
latency samples.

## Cold/warm definitions

- Cold container: new container/process and unloaded filesystem cache; model download reported
  separately.
- Warm container, model unloaded: process is alive but weights are not resident.
- Warm loaded: weights are resident before the measured call.
- First CUDA: first kernel execution after load.
- Steady state: warmed kernels and resident model.

Cold-container orchestration is deployment-specific and must be implemented by the benchmark
adapter/supervisor; a normal Python function call must not be labeled a cold container. For the
`cold_container` phase, the adapter must return `container_restarted: true`. Otherwise the harness
records the sample as `INVALID`, not `MEASURED`.

## Workloads

`image_benchmark.py`, `video_benchmark.py`, and `lipsync_benchmark.py` contain fixed, serialized
profiles. Any change creates a new profile rather than silently altering a result. Lip sync is
exactly 10 seconds at 25 FPS. Video specifies five seconds/120 frames at 1280×720/24 FPS and an
8+3 candidate schedule. The adapter records all actual values; candidates are not measurements.

## Statistics and maximum

Warmups are discarded. Results include p50/p90/p95/p99, mean, lowest, and highest observed. The
highest observed value is only the maximum completed sample. Target, SLO, timeout, and measured
statistics are separate fields. Failed runs remain failures and are not silently retried.

## Outputs

The harness writes environment/gpu profiles, raw JSONL, summary JSON/CSV, Markdown, and charts. An
empty chart means no measured data. Environment capture records missing fields as null/UNVERIFIED.
Cost uses a dated operator-supplied rate; no provider rate is hardcoded.

## A10G

Run the exact same images, versions, checkpoint, seeds, precision, settings, and counts on actual
A10G hardware. If absent, report `NOT TESTED`; do not scale RTX 5090 results or substitute vendor
specifications.
