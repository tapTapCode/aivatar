# Phase 3 — Presenter + Composition

Phase 3 connects presenter generation to the authoritative master-audio timeline and adds local FFmpeg composition for presenter-led scenes.

## Implemented

- `AuthorizedHeyGenProvider`
  - authorized API-key flow only
  - current v3 API support for Avatar IV/V
  - maintained legacy v2 generation path retained for the project's Avatar III requirement
  - audio is uploaded as an asset, and only the exact presenter scene audio segment is submitted
  - asynchronous status polling and output download
  - no browser/session automation and no billing/credit bypass
- `MuseTalkFallbackProvider`
  - RunPod Serverless + R2 transport
  - MuseTalk 1.5 worker wrapper
  - worker downloads model dependencies on ephemeral storage rather than relying on a persistent model volume
- `ManualPresenterImportProvider`
  - normalizes an imported clip into silent H.264 for the requested scene duration
- presenter job orchestration
  - independent presenter concurrency semaphore
  - project-wide presenter generation
  - single-scene regeneration
  - locked assets/scenes prevent destructive regeneration
  - presenter assets and costs are persisted per scene
- master narration segmentation
  - exact start/end slice per presenter scene
  - final editor ignores presenter-returned audio
- FFmpeg presenter composition
  - full presenter
  - SPLIT 50/50, 40/60, 35/65
  - presenter left/right
  - rounded presenter mask
  - border and margins
  - PIP positions, size, margins, shadow, border, corner radius
- scene preview endpoint
  - re-renders only the requested scene
  - changing/regenerating a presenter invalidates only that scene's cached preview
- `layout_json` on scenes for durable presentation settings

## HeyGen version boundary

The application does not expose HeyGen API details to the rest of the pipeline. `HEYGEN_API_MODE=legacy_v2` is the default because the agreed presenter target is Avatar III. A channel can later switch to the v3 API and Avatar IV/V without changing timeline or render code.

The legacy API is intentionally isolated because it is on a deprecation path. Aivatar should migrate individual channel configurations when the approved replacement meets the desired presenter quality.

## Proof

`python scripts/render_phase3_mock_project.py --duration 60`

The proof uses exactly 30% presenter visibility and exercises `PRESENTER`, `SPLIT`, and `PIP`, while the final MP4 is mixed against one master narration track.
