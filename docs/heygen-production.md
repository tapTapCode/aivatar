# HeyGen production avatar backend

Status: `VERIFIED` by mocked contract tests; live funded generation is `NOT TESTED`.
Staging `/health` reports `avatar_video_provider=heygen_api`. `HEYGEN_API_KEY` is still
missing from Preview, so catalog and export stay empty until the official key is added to
the Vercel secret store. The API does not fail startup when the key is empty.

HeyGen is a backend implementation detail. The operator UI submits the existing
Exact Scene project contract and never receives the provider API key or HeyGen
account controls. Provider provenance remains available in internal asset records
for cost, licensing, and operational audits.

## Data flow

1. In the default `native` voice mode, the backend submits the scene script,
   approved `voice_id`, and approved `avatar_id` directly to the provider.
2. The backend calls the official `POST /v3/videos` endpoint.
3. The provider polls `GET /v3/videos/{video_id}` with a bounded timeout.
4. The completed MP4 is downloaded before its temporary URL expires and validated
   with FFprobe.
5. Presenter audio is extracted from the licensed MP4 for downstream scene composition;
   Chatterbox is not invoked for native presenter scenes.
6. When enabled, the MP4 is uploaded to private Cloudflare R2 and verified by
   byte count plus SHA-256 object metadata before the scene continues.
7. Exact Scene performs its normal captions, visuals, FFmpeg assembly, and final
   validation.

The optional `audio` voice mode uploads authorized narration to `POST /v3/assets` and
passes the resulting asset ID to the video request.

## Configuration

Install S3 support when R2 retention is enabled:

```bash
python -m pip install -e '.[s3]'
```

Set these values only in the deployment secret store. Never put the API key or
R2 credentials in web assets, project JSON, logs, git remotes, or committed env
files.

```dotenv
PROVIDER_MODE=workers
AVATAR_VIDEO_PROVIDER=heygen_api
HEYGEN_API_KEY=<rotated-server-side-key>
HEYGEN_API_BASE=https://api.heygen.com
HEYGEN_ENGINE=avatar_iv
HEYGEN_VOICE_MODE=native
HEYGEN_RESOLUTION=1080p
HEYGEN_RATE_USD_PER_MINUTE=4.0
HEYGEN_MAXIMUM_COST_USD_PER_JOB=25.0
HEYGEN_POLL_INTERVAL_SECONDS=10
HEYGEN_TIMEOUT_SECONDS=7200
HEYGEN_R2_RETENTION_ENABLED=true
HEYGEN_R2_PREFIX=retained/heygen
S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
S3_BUCKET=<private-bucket>
S3_ACCESS_KEY=<bucket-scoped-access-key>
S3_SECRET_KEY=<bucket-scoped-secret>
```

Use `local_musetalk` for `AVATAR_VIDEO_PROVIDER` to return to the local GPU
worker path.

## White-label boundary

The customer UI and public asset API use Exact Scene terminology and do not expose the
upstream provider name, API key, provider job ID, storage path, or internal provenance.
Original provider details remain in private asset records and server logs for support,
licensing, spend reconciliation, and audits. The product must not claim that the underlying
avatar model is owned by Exact Scene, and provider watermarks may only be absent when the
account's licensed export plan permits it.

## Spend guard

The API rejects a project before queueing when its estimated total presenter
time would exceed `HEYGEN_MAXIMUM_COST_USD_PER_JOB`. The provider also keeps a
second per-job reservation ledger, preventing multiple presenter scenes from
silently exceeding the same limit during execution.

At the configured Avatar IV rate of $4/minute, a $25 ceiling allows at most
6.25 minutes of presenter footage. Topic-visual scenes do not consume HeyGen
avatar minutes.

The estimate is a guard, not a billing statement. Record the provider's actual
charge after the live run.

## Production gate

Before enabling this provider for clients:

1. Rotate every API/R2 credential that has appeared outside its secret store.
2. Fund the HeyGen API wallet.
3. Confirm the approved avatar ID exists on the same API workspace.
4. Run one 10–15 second paid canary with a maximum cost below $2.
5. Verify the downloaded MP4, R2 object, checksum, duration, resolution, audio,
   and provider charge.
6. Only then raise the per-job ceiling for the first long-form render.
