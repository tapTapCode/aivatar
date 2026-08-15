# Aivatar AI Video Pipeline

A code-first control plane and FFmpeg rendering pipeline for videos with three hard scene
contracts: `PRESENTER`, `SPLIT`, and `FULL_VISUAL`. Production execution does not depend on
ComfyUI or browser automation.

The default avatar engine is HeyGen (`AVATAR_VIDEO_PROVIDER=heygen_api`). The official API
key stays server-side. Staging health reports `heygen_api` even when `HEYGEN_API_KEY` is
still missing; export waits until the key is in the Vercel secret store. See
[`docs/heygen-production.md`](docs/heygen-production.md) and
[`docs/vercel-deployment.md`](docs/vercel-deployment.md). Browser automation is not used.

For a zero-API-cost proof, use the authorized watermarked MP4 import path documented in
[`docs/free-heygen-proof.md`](docs/free-heygen-proof.md). The source watermark is preserved.

The repository currently provides a fully testable mock path, strict Pydantic contracts,
provider boundaries, job state transitions, content-addressed caching, FastAPI endpoints,
Redis/in-memory queues, FFmpeg composition, isolated Docker worker definitions, and an honest
GPU benchmark harness. Real FLUX.2, LTX-2.3, Chatterbox, and MuseTalk runs require separately
configured workers, licensed/authorized inputs, model revisions, and NVIDIA hardware.

## Quick start

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
python -m scripts.generate_demo --project examples/three-format-project.json
uvicorn src.api.main:app --host 127.0.0.1 --port 8001

# In a second terminal:
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

The host must have `ffmpeg` and `ffprobe`. Docker and GPU deployment commands are in
[`docs/deployment-runbook.md`](docs/deployment-runbook.md). The generated mock demonstration is
clearly labeled and does not claim model or avatar quality.

The Next.js operator dashboard runs at `http://localhost:3000` and proxies API requests to the
FastAPI service on `http://127.0.0.1:8001`. It is protected by database-backed email/password,
Google, and Apple authentication. Local setup and Neon, Resend, and OAuth deployment variables
are documented in [`docs/authentication.md`](docs/authentication.md).

## Local presenter studio

The operator UI includes a **Presenter studio**. The team pastes or picks a HeyGen avatar ID,
approves the script, and HeyGen exports the presenter MP4. MuseTalk remains an optional local
fallback, not the default. See [`docs/vercel-deployment.md`](docs/vercel-deployment.md) for
staging aliases and [`docs/local-presenter-pipeline.md`](docs/local-presenter-pipeline.md) for
the optional GPU path.

## Exact routing guarantee

| Format | Speech | Avatar source | Lip sync | Visual generation | Composition |
| --- | --- | --- | --- | --- | --- |
| `PRESENTER` | required | required | required | forbidden | avatar only |
| `SPLIT` | required | required | required | required | configured split |
| `FULL_VISUAL` | required | forbidden | forbidden | required | visual only |

Unknown schema fields are rejected. Scene order is normalized deterministically after duplicate
orders are rejected. Every asset includes scene lineage and provider provenance.

## Status vocabulary

Documentation and benchmark reports use `VERIFIED`, `OBSERVED`, `INFERRED`, `UNVERIFIED`, and
`NOT TESTED`. No synthetic mock timing is presented as a GPU/model benchmark.
