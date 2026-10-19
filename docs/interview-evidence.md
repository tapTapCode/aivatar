# Interview evidence: Aivatar video pipeline

Updated 20 October 2026. This document is an interview handoff, not a claim of exact
FaceTuber/FaceTube parity.

## Representative code

Source handoff: the representative implementation is in this Aivatar project. A public
repository link has not been verified, so do not send the old GitHub URL unless a working
repository is created and reviewed first.

The Aivatar implementation keeps presenter providers behind a common interface in
`pipeline/providers/presenter.py`. It supports authorized HeyGen and Higgsfield
requests, a local/remote MuseTalk fallback, and an explicit manual presenter-clip
import path. The render path plans scenes, generates presenter material only for
presenter-bearing scenes, composes `PRESENTER`, `SPLIT`, and `FULL_VISUAL` layouts
with FFmpeg, and records render metadata and cost entries.

The story form now persists a six-scene visual plan. Each scene can be marked as
`PRESENTER`, `SPLIT`, or `FULL_VISUAL`, and its visual direction is patched into the
backend plan before rendering. Long presenter scenes are split into provider-safe
audio chunks, with a JSON checkpoint beside each generated clip so a failed or
interrupted run can reuse completed chunks.

Verification run:

```text
Frontend: `pnpm build` — passed
Backend: targeted presenter/API/provider tests — passed
Production smoke export: H.264/AAC, 1920×1080, 30 fps, 11.943 seconds, completed at $0

## Best current playable sample

Use the clean Higgsfield presenter segment included in the interview handoff package:

`workspace/projects/d5c6870c-03f8-4eda-9b4b-aa8cc1a5e100/presenter/presenter_b11b3bf4-f7e3-406a-bafd-705967aa5e48.mp4`

This is an authorized Higgsfield `wan/v2.7/image-to-video` presenter export with uploaded
scene audio and a reference image. It is suitable as a short talking-presenter example.
The 160-second composite from the same project is retained for internal debugging only
because some B-roll sections are blank and should not be sent as the finished sample.
```

## What I personally built

- Provider adapters, upload/poll/download flows, and server-side credential handling.
- Scene planning and the FFmpeg composition path.
- Presenter-provider routing between authorized HeyGen, Higgsfield, local fallback,
  and manual imports.
- Scene-level story editing and long-form presenter chunking/checkpointing.
- Cost guards, output validation, and failure-path tests.

AI coding tools were used for boilerplate suggestions and debugging assistance. The
architecture, provider boundaries, render decisions, failure handling, and test
verification were reviewed and integrated manually.

## Video examples and permissions

Use a clean playable export or an authenticated staging link for the final examples.
The earlier Higgsfield/Kling test clip contained visible frame artifacts, so it should not
be presented as the best finished sample. The clean presenter segment above is the safer
demo.

Presenter images, voices, and generated media should only be shared when they are
owned by the applicant, supplied by the client, or covered by explicit permission.
No private credentials, personal-account access, browser-session automation, or
watermark-removal workflow belongs in the submission.

## Honest limitation

The current local end-to-end smoke export used real scene planning, captions, FFmpeg
composition, and a local macOS voice fallback because the configured AI33 key returned
401. It did not include a presenter. The clean Higgsfield segment demonstrates the
presenter path, but full long-form avatar quality, phoneme-level lip-sync, and all-scene
continuity still need a fresh authorized provider run and a side-by-side QC pass.
