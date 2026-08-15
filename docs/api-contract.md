# API Contract

Base version: `v1`. Requests and responses reject unknown schema fields.

## Endpoints

- `POST /v1/projects`: validate/store a `ProjectScript` as `draft`. Client `approval_state` is ignored.
- `PUT /v1/projects/{project_id}`: replace a stored script and reset it to `draft`.
- `POST /v1/projects/{project_id}/approve`: mark the stored script approved.
- `POST /v1/videos`: queue an approved stored `ProjectScript`, require `Idempotency-Key`, and immediately
  return `{video_id, job_id, status, watermark_status}` with HTTP 202. Unsaved or unapproved scripts
  return HTTP 422.
- `GET /v1/videos`: owner-scoped job list. Also schedules recovery of one stranded `QUEUED` job.
- `GET /v1/videos/{video_id}` and `GET /v1/jobs/{job_id}`: owner-scoped job state/history. A `QUEUED` job is reclaimed if the original consumer died.
- `POST /v1/videos/{video_id}/cancel`: owner-scoped cancellation.
- `GET /v1/assets/{asset_id}`: owner-scoped asset metadata/provenance. A production S3 adapter
  should return short-lived signed download URLs separately.
- `GET /health`, `GET /ready`, `GET /metrics`.

`X-API-Key` is enforced when `API_KEY` is configured. `X-Owner-Id` defaults only in development;
production authentication middleware must derive ownership from a verified identity, not trust a
caller-supplied header.

When `PROVIDER_MODE=workers`, every used voice and avatar must have a matching, timezone-stamped
consent record unless the corresponding operator policy flag is explicitly disabled. Evidence URIs
are metadata references; a hardened deployment must independently verify and retain the evidence.

## Scene rules

- `PRESENTER`: non-empty narration, `avatar_id`, no `visual_description`.
- `SPLIT`: non-empty narration, `avatar_id`, and `visual_description`.
- `FULL_VISUAL`: non-empty narration and `visual_description`, no `avatar_id`.
- `schema_version` is mandatory and currently exactly `1.0`.
- Orders and IDs are unique; scenes are sorted deterministically by order then ID.
- `approval_state` is `draft` or `approved`. Saves always store `draft`; rendering requires a matching approved script.

## Example

```bash
curl -X POST http://127.0.0.1:8001/v1/projects \
  -H 'Content-Type: application/json' \
  -H 'X-Owner-Id: operator-1' \
  --data-binary @examples/three-format-project.json

curl -X POST http://127.0.0.1:8001/v1/projects/three_format_demo/approve \
  -H 'X-Owner-Id: operator-1'

curl -X POST http://127.0.0.1:8001/v1/videos \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-request-0001' \
  -H 'X-Owner-Id: operator-1' \
  --data-binary @examples/three-format-project.json
```

Provider results include IDs, URI, SHA-256, scene/parent lineage, media properties, timestamps,
model/revision/configuration, prompt/seed when applicable, stage latency, VRAM fields, retry count,
and warnings.

## Clean-export routing

`ProjectScript.require_clean_export` defaults to `false`. When enabled, job validation accepts only
an authorized clean-output provider (`heygen_api` or `local_musetalk`). The `imported_video`
provider always preserves its source watermark and is rejected before cleanup, queueing, FFmpeg,
or provider allocation when a clean export is required:

```json
{
  "error": "UNLICENSED_WATERMARK_REJECTION",
  "message": "Cannot satisfy clean export request with watermarked free source media. Please select an authorized provider (HeyGen API or local GPU)."
}
```

Creation and status responses expose `watermark_status` as either `PRESERVED` or
`CLEAN_AUTHORIZED`. Private R2 uploads persist this value as object metadata alongside SHA-256 and
the verified byte length.
