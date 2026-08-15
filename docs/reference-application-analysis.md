# Reference Application Analysis

Analysis date: 2026-07-15. Scope was limited to public pages. No authentication, private endpoint,
source map, token, customer data, or protected source code was accessed.

## Public observations

The public [FaceTuber landing page](https://facetuber.ai/) describes a character-driven AI video
studio for faceless YouTube workflows. It publicly claims a workflow involving reusable characters,
faces/voices/personas, narration, talking heads, b-roll, music, and end-to-end assembly. These are
`OBSERVED` product statements, not independent verification of output quality, usage metrics, or
backend behavior.

The public [FaceTuber terms](https://facetuber.ai/terms) describe script-supplied, full-length,
character-driven video generation and say the service orchestrates several third-party AI services.
This is `OBSERVED` legal/product disclosure. It does not establish the private implementation,
request schemas, queue topology, model versions, or checkpoints.

## Observable workflow

| Statement | Classification |
| --- | --- |
| A user supplies or operates from a script/content concept. | OBSERVED from public terms/marketing. |
| The product presents reusable character creation as a step. | OBSERVED from public landing page. |
| The marketed output combines narration, talking head, b-roll, and music. | OBSERVED. |
| Jobs are asynchronous with visible job status. | UNVERIFIED; authenticated application was unavailable. |
| Users can directly control exact presenter/split/full-visual scene types. | UNVERIFIED. |
| Backend uses a control plane plus queued model workers. | INFERRED as a reasonable pattern, not a FaceTuber fact. |
| Backend uses FLUX, LTX, MuseTalk, Chatterbox, or ComfyUI. | UNVERIFIED and not asserted. |

## Features worth recreating lawfully

- Script-to-timeline workflow.
- Reusable, authorized character and voice identities.
- Talking-head and supporting-visual composition.
- Narration, b-roll, music, captions, and export as replaceable stages.
- Asynchronous job creation, clear state, retries, and deterministic scene lineage.

This repository recreates only general workflow concepts and the user-supplied three-format
contract. It does not copy FaceTuber branding, UI, prompts, private endpoints, code, assets,
videos, or product-specific visual identity.

## Legal and technical boundary

Public marketing claims are not evidence of internal architecture. Any future authenticated review
must use a client-authorized account and normal browser developer tools, restrict capture to that
account's own traffic, avoid secrets in documentation, and stop before payment, access-control, or
rate-limit circumvention. Proprietary implementation details must not be reproduced.

