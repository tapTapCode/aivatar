# Modal background HeyGen exporter

This is the production split for authorized, clean presenter exports:

```text
Aivatar on Vercel → signed Modal ingress → background Modal export function
       ↑                     ↓                         ↓
 job status callback       queue                    HeyGen + FFmpeg
       ↑                                               ↓
       └──────────── private Cloudflare R2 final MP4 ─┘
```

`modal_heygen_worker.py` deliberately supports a first **PRESENTER-only**
canary. It invokes the official HeyGen API, extracts the authorized presenter
audio, uses FFmpeg for the final MP4, validates the result, and uploads it to
private R2 with checksum metadata. Modal is billed only while the job runs.

## Required secrets

Create a Modal secret named `aivatar-production` with:

```text
HEYGEN_API_KEY=<newly rotated official key>
HEYGEN_ENGINE=avatar_iv
HEYGEN_VOICE_MODE=native
HEYGEN_RESOLUTION=4k
HEYGEN_RATE_USD_PER_MINUTE=4.0
HEYGEN_MAXIMUM_COST_USD_PER_JOB=2.0
S3_ENDPOINT_URL=https://<cloudflare-account-id>.r2.cloudflarestorage.com
S3_BUCKET=<private-r2-bucket>
S3_ACCESS_KEY=<r2-access-key>
S3_SECRET_KEY=<r2-secret>
FINAL_VIDEO_R2_PREFIX=videos
MODAL_DISPATCH_SECRET=<long-random-shared-secret>
```

Then deploy from a trusted workstation:

```bash
python -m pip install modal boto3
modal setup
modal deploy modal_heygen_worker.py
```

Set the produced Modal ingress URL and the same dispatch secret in the Aivatar
control plane. Use `BACKGROUND_RUNNER=modal`, `MODAL_DISPATCH_URL`,
`MODAL_DISPATCH_SECRET`, and a `MODAL_CALLBACK_URL` ending in
`/v1/internal/modal-jobs/{job_id}`.

## Production gate

Before enabling `BACKGROUND_RUNNER=modal` in Vercel, replace the current
in-memory `ControlPlaneRepository` with a durable Postgres repository. Serverless
memory cannot reliably retain job records across invocations, so a live Vercel
deployment must not use the callback status path until that repository is in
place.

Run one consented 10–15 second presenter project with an approved avatar and
voice ID. Confirm the R2 checksum, resolution, audio, watermark status, and
provider charge before raising the per-job cost cap.
