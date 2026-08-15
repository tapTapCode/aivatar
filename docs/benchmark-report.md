# Benchmark Report

Report date: 2026-07-15

| Workload | RTX 5090 | A10G | Reason |
| --- | --- | --- | --- |
| FLUX.2 fixed image | NOT TESTED | NOT TESTED | No NVIDIA GPU, model weights, or pinned adapter. |
| LTX-2.3 fixed video | NOT TESTED | NOT TESTED | No NVIDIA GPU, model weights, or pinned adapter. |
| MuseTalk 10-second lip sync | NOT TESTED | NOT TESTED | No NVIDIA GPU or authorized fixed media. |
| Attention/cache configurations | NOT TESTED | NOT TESTED | Pinned implementations unavailable. |
| PagedAttention | NOT APPLICABLE pending workload inspection | NOT APPLICABLE pending workload inspection | No verified request-growing autoregressive token-KV workload. |

No GPU latency, throughput, VRAM, power, quality, or cost number has been measured or estimated.
The reproducible CLI is implemented; run it on the target host and commit only small reports, not
checkpoints or generated videos.

