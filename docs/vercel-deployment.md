# Aivatar Vercel deployment

Use two Vercel projects:

- The repository root deploys the API-only FastAPI service through `api/index.py`.
- `frontend/` deploys the Next.js browser application.

Set a stable backend alias such as `aivatar-api-staging.vercel.app`. In the frontend project,
set `FASTAPI_ORIGIN=https://aivatar-api-staging.vercel.app`. In the backend project, set
`APP_BASE_URL` and `ALLOWED_ORIGINS` to the public frontend URL. Neon, Resend, OAuth, worker,
queue, and storage secrets belong only to the backend project. Local `.env` files are excluded
from Vercel uploads; serverless Settings read Vercel environment variables only.

The frontend proxies `/v1/*`, `/health`, `/ready`, and `/metrics` to FastAPI. Browser cookies
therefore remain scoped to the frontend host and CSRF origin checks see the public application
origin.

Deploy the backend from the repository root, then deploy the frontend with `frontend/` selected
as its Vercel root directory. Verify a preview deployment before assigning the stable frontend
alias.

Current staging aliases:

| Role | URL | Vercel project |
| --- | --- | --- |
| Next.js workspace | https://aivatar-staging.vercel.app | `aivatar-web` |
| FastAPI control plane | https://aivatar-api-staging.vercel.app | `aivatar` |

`FASTAPI_ORIGIN` on `aivatar-web` must be available at build time so Next.js can rewrite `/v1`,
`/health`, `/ready`, and `/metrics` to the API host. Neon remains attached only to FastAPI.
Resend and Google/Apple still require their provider secrets before those external flows can
complete.

## Staging health (15 Aug 2026)

`GET /health` on both staging aliases reports `avatar_video_provider=heygen_api`. The control
plane boots on that default without a HeyGen key. `HEYGEN_API_KEY` is still missing from
Preview. Preview env add is refused unless the Vercel project has a Git branch, and `aivatar`
has no Git connection.

| Check | Result |
| --- | --- |
| `https://aivatar-api-staging.vercel.app/health` | `200`, `avatar_video_provider=heygen_api` |
| `https://aivatar-staging.vercel.app/health` | same payload through the Next.js rewrite |
| `HEYGEN_API_KEY` on Preview | missing |
| Empty key at boot | `/health` stays `ok`; `heygen_configured=false`; catalog is empty |
| Live HeyGen export | waits until the official key is in the Vercel secret store |

Do not commit `.env` or paste the key into chat. Do not run `vercel deploy --prod -e ...` on
the API project; that replaces Production env and can drop `DATABASE_URL`. To add the key
later, set it as a sensitive Production (and Preview, once a git branch exists) variable in
the `aivatar` project only.

## Important production boundary

Vercel hosts the web and API edges, not the GPU rendering worker. Its filesystem and in-memory
repository are ephemeral, and serverless functions are not the correct place for FFmpeg, model
downloads, or long-running video jobs.

Before enabling real video creation on the deployed site, configure:

- a durable project/job repository (Postgres) — Neon is live; stranded `QUEUED` jobs are reclaimed from that store;
- a durable queue (Redis or managed queue) for multi-instance fan-out; Neon recovery covers single-consumer cold starts;
- Cloudflare R2 for uploaded and generated media;
- external GPU worker URLs for TTS, image, motion, lip-sync, and render stages;
- Vercel environment variables for the API key, storage credentials, and worker URLs.

Without those services, the deployment is suitable for the Aivatar UI and API contract validation only. It must not be represented as a production rendering environment.
