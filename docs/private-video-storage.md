# Private final-video storage

Exact Scene keeps final MP4 files in a private Cloudflare R2 bucket when
`STORAGE_BACKEND=r2`. The application stores only the private object identity internally and uses
short-lived, owner-scoped downloads. API credentials are server-side only.

## Configuration

```dotenv
STORAGE_BACKEND=r2
S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
S3_BUCKET=exact-scene-videos
S3_ACCESS_KEY=<server-side access key>
S3_SECRET_KEY=<server-side secret>
FINAL_VIDEO_R2_PREFIX=videos
RETAINED_DOWNLOAD_URL_SECONDS=900
```

Use R2 Standard storage for actively downloaded videos. Keep the bucket private and grant the
application token object read/write access only to this bucket.

Final objects use this deterministic layout:

```text
videos/{owner_id}/{project_id}/{video_id}/final.mp4
```

Every upload is verified against its byte length, SHA-256, and `watermark_status` object metadata
before a job is marked complete. If the temporary local copy expires, the download endpoint
redirects to a short-lived R2 URL. The customer UI exposes only whether the output is privately
retained and whether its watermark is preserved or clean-authorized, never its provider, bucket,
key, or credentials.

## Upload an existing proof

```bash
python -m scripts.upload_final_to_r2 \
  outputs/free-heygen-proof-exact-scene.mp4 \
  --owner local-development \
  --project free_heygen_proof \
  --video vid_4e46b564ca1e41fa91658e755bc096e9
```

Exact Scene preserves watermarks embedded in imported source videos. It does not include a
watermark-removal workflow. For a clean deliverable, supply an authorized unwatermarked source or
use an official provider export that includes clean-output rights.
