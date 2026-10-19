# Implementation status — 19 October 2026

Reference: FaceTuber public landing page, inspected during this task. Its signed-in product and proprietary models were not available for comparison. Marketing claims about views, retention and sales are not implementation guarantees.

| Advertised capability | Delivered in this source update | Remaining work / practical limit |
| --- | --- | --- |
| Reusable character: face, voice, persona | Persistent profiles, uploads, image-provider portrait generation, saved voice IDs, editable persona | No custom voice cloning or avatar training. Persona guides presenter motion but does not rewrite narration. Provider quality must be checked live. |
| Script to full video | Integrated approved production job with progress | Current director is deterministic; semantic LLM scene direction and automated scriptwriting remain future work. |
| Talking head | Routes to selected existing HeyGen/Higgsfield adapter; preserves selected voice ID | No live lip-sync, identity or realism validation was performed. Provider contract/account validation is still required. |
| Supporting footage | Script-derived prompts, generated stills, motion, split composition | New automatic path uses still-image motion. Existing LTX adapter remains in advanced backend; selecting generative moving B-roll in the new UI is not implemented. |
| Narration | Existing TTS adapters or imported audio | AI33/69Labs adapters are generic configurable contracts; provider testing and multilingual voice verification remain. No voice-sample browser yet. |
| Music / audio scoring | Uploaded music mixed under narration with ducking and normalization | Automatic music generation, licensed music catalog and semantic music selection are not implemented. |
| Full-length videos | Dynamic scene count, saved stage progress, asset reuse, up to two-hour script estimate | Only short local demo renders were tested; no two-hour endurance or provider-quota test. Transitions are cuts, not cinematic generated transitions. |
| Multiple channels | Persisted channels and per-channel characters/productions | All channels belong to one local operator; no remote tenancy. Channel edit endpoint exists; UI currently creates/selects channels. |
| Concurrent generation | Existing resource limits and durable jobs integrated with new workflow | Provider requests already in flight cannot be cancelled. Paid jobs interrupted by restart require manual review to avoid automatic duplicate charges. |
| Team seats | Not implemented as a hosted feature | Needs real authentication, invitations, role enforcement, shared storage and tenant-safe API. Existing legacy local account screens are not real team identity. |
| Monthly credits / subscriptions / prepaid packs | Real local runtime and reported-usage visibility | No payment processor, subscription renewal, credit ledger, prepaid checkout or billing webhooks. These need a business model, merchant account and hosted backend. |
| Channel growth / automated publishing | Not claimed | No YouTube OAuth upload/scheduling, analytics or growth guarantee. Public “channel runs itself” wording does not establish that FaceTuber exposes those exact APIs. |

## Important source repairs

- Restored `pipeline/cache/assets.py`, which was missing from the supplied cleaned archive and prevented API imports.
- Isolated mock-media cache keys and rejected known mock cache entries on production generation.
- Preserved `voice_id` in avatar creation (the previous schema silently ignored it).
- Prevented selecting an avatar from a different channel.
- Removed fixed $0.25 values from the workspace cost view and corrected the false healthy status when the API is offline.
- Replaced hard-coded registered media and the fictional account-avatar catalog with saved avatars. Remote account discovery remains future work.
- Fixed a missing-avatar crash in the existing demo presenter service and gave demo presenter clips unique scene filenames.
- Added a backwards-compatible production-options migration plus an Alembic migration.
- Changed `main.py` from a paid provider example to the actual local API launcher.

## Recovery and cost boundaries

Successful narration and presenter clips are persisted. Visual source cache is reused after interruption; composition can run again. Every paid external request cannot yet be reconciled with a durably stored provider request ID, so paid automatic jobs are not silently restarted after a crash. Check the provider account for outstanding jobs before using Review / continue. Already completed assets will be reused. A completed production cannot be accidentally queued again through the same generate endpoint.

Preflight uses estimated speech length. Actual narration may be longer. The legacy per-presenter guard still applies during execution. It is not a price quote or hard account spending cap. Account-level spend limits remain with the provider.

Captions use provider timestamps when supplied, with heuristic word timing otherwise. This is not forced alignment; inspect subtitle timing before publishing. The custom pink/color setting changes split-layout backgrounds, not pixels behind an actor in a generated full-frame clip.

## Validation limits

The code was built and tested in an isolated Linux workspace. The user's live app at 127.0.0.1:1420 was inspected earlier but was not changed. No Mac/Tauri package was signed or built, no production provider credits were used, and no remote service was deployed. Browser interaction with the new build on the user's machine remains a local installation check.

