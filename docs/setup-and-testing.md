# Setup and testing

Last updated: 2026-08-15 (Asia/Manila)

## Product paths

| Path | Role |
| --- | --- |
| Repository root | Aivatar FastAPI control plane |
| `frontend/` | Next.js operator workspace |
| `local-ai-video-pipeline-proof/` | Newest production requirements, RunPod/R2 proof path |
| `ClipNET-2-fix/` | Out of scope for this product |

## Local control-plane setup

```bash
cd ~/Documents/Youtube
python3.12 -m venv .venv   # or existing .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Host requirements: `ffmpeg` and `ffprobe` on `PATH`.

## Run API + operator workspace

```bash
uvicorn src.api.main:app --host 127.0.0.1 --port 8001

# second terminal
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000/` for the operator workspace.  
API docs: `http://127.0.0.1:8001/docs`.

Staging: `https://aivatar-staging.vercel.app` (UI) and
`https://aivatar-api-staging.vercel.app` (API). `GET /health` reports
`avatar_video_provider=heygen_api`. `HEYGEN_API_KEY` is still missing from Preview, so
`heygen_configured` is false on keyless boots and live export waits. See
[`vercel-deployment.md`](vercel-deployment.md).

## Mock demo (CLI)

```bash
python -m scripts.generate_demo --project examples/three-format-project.json
```

## Validation executed 2026-08-06

| Command | Result |
| --- | --- |
| `python -m pytest tests/test_api.py tests/test_routing.py tests/test_state_machine.py -q` | **7 passed** |
| `ruff check src/api/main.py src/api/repository.py tests/test_api.py` | **All checks passed** |
| Import `src.api.main:app` | **OK** (18 routes) |
| End-to-end GPU 10-min / 30-min generation | **Not run** (costly; not authorized in session) |
| R2 rclone list (`local-ai-video-models`) | **Pass earlier today** (empty bucket) |

## New API surfaces

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | API service metadata |
| GET | `/v1/projects` | List owner projects |
| GET | `/v1/projects/{project_id}` | Fetch one project |
| GET | `/v1/videos` | List owner jobs/videos |

## R2 operator credentials (proof subtree only)

Use gitignored `local-ai-video-pipeline-proof/.env.r2.local`. Never commit secrets. Bucket `local-ai-video-models` holds `local-bootstrap-20260806` and `models-avatar-20260806` (20.2 GiB, restore manifest added 2026-08-15).
