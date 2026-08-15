# Latest Technology Stack and Delivery Direction

**Source:** Full WhatsApp conversation with Jorge Luis, reviewed chronologically through August 12, 2026  
**Prepared:** August 12, 2026  
**Scope:** The latest agreed production direction, superseded proposals, current repository alignment, and remaining validation work.

## Executive summary

The latest product direction in the conversation is a **HeyGen-first, provider-agnostic documentary presenter pipeline**. Each channel supplies its own authorized presenter reference image or selects an approved HeyGen avatar. HeyGen is the preferred primary presenter renderer because avatar realism is the client's highest priority. The pipeline then combines the returned presenter MP4 with topic visuals, captions, motion graphics, and narration using the exact `PRESENTER`, `SPLIT`, and `FULL_VISUAL` scene formats.

The supported production integration must use the **official HeyGen API and legitimately funded account access**. The browser/Developer-Tools credit-bypass method discussed later in the conversation is not an acceptable production interface. The reusable local-motion plus MuseTalk implementation remains the fallback and cost-control path if official HeyGen pricing is not acceptable.

The primary local stack is:

- **HeyGen native voices** for the minimal presenter workflow; the script and approved voice ID are sent server-side.
- **Chatterbox** only as an optional external-audio/voice-cloning path for authorized voices or non-presenter scenes.
- **Faster Whisper** only when external transcription, word timing, or captions are required.
- **Official HeyGen API** as the primary avatar/presenter renderer.
- **MuseTalk 1.5** for the local fallback lip-sync path.
- **FLUX.2 Klein 4B Distilled** for presenter setup images and topic imagery.
- **LTX-2.3 Distilled/Flash** as the current candidate for one-time presenter motion generation, subject to a strict realism gate.
- **FFmpeg** for deterministic scene rendering, captions, graphics, audio normalization, assembly, and final delivery.
- **FastAPI + Pydantic** as the control plane and scene-contract API.
- **Redis-backed jobs** for production queues, retries, and resumable long-form work.
- **Isolated Docker workers** for speech, image, motion, lip sync, and rendering.
- **Temporary RunPod NVIDIA workers** for GPU stages; no idle persistent GPU volumes.
- **Hugging Face** as the latest requested source for pinned model revisions inside containers.
- **Cloudflare R2** for durable outputs, manifests, checksums, reports, and optional verified caches—not as an unversioned model dump.

HeyGen is therefore the **primary avatar provider**, while the application remains provider-agnostic so the local stack can be selected per project. Browser/Developer-Tools credit bypasses, shared anti-detect browser profiles, unauthorized downloading, and watermark removal are not reliable or acceptable production architecture.

## Latest confirmed product requirements

| Requirement | Latest interpretation |
|---|---|
| Final duration | The MVP must prove one **30–40 minute** video, not merely a 10-minute demo. |
| Channel scale | The same pipeline must support many channels and many distinct avatars. |
| Presenter source | Jorge chooses each presenter and supplies an authorized reference image or approved source footage. |
| Presenter quality | Natural head, shoulder, and hand movement comparable in realism and pacing to the reference channels. |
| Motion continuity | Presenter shots should be at least 10 seconds, with no internal cuts, pauses, freezes, or visible loops. |
| Scene contract | Preserve exact `PRESENTER`, `SPLIT`, and `FULL_VISUAL` behavior. |
| Editorial style | Documentary-presenter pacing with topic images, captions, motion graphics, text, and restrained effects. |
| Reusability | Motion generation is primarily a one-time per-avatar setup cost; approved motion clips are reused and re-lip-synced. |
| Cost | Make recurring video generation as inexpensive as possible and measure actual cost; the earlier `$1–$2` target is not yet proven. |
| Output quality | Produce at a stable working resolution and upscale once at delivery only when the quality gain justifies time and cost. |
| Operations | Jobs must be resumable, cacheable, observable, and safe to retry at scene/chunk level. |

## Recommended production architecture

### 1. Planning and scene specification

Use a versioned JSON/Pydantic project schema. A script is divided into deterministic scenes, and every scene declares one of three layouts:

- `PRESENTER`: presenter plus narration.
- `SPLIT`: presenter and supporting visual side by side plus narration.
- `FULL_VISUAL`: supporting visual plus narration, without the presenter.

Long-form work should be divided into restartable narration and lip-sync chunks. Keep presenter takes continuous for at least 10 seconds while allowing topic visuals to change independently.

### 2. Voice and alignment

1. For the minimal presenter workflow, submit the script and approved voice ID through the official HeyGen API.
2. Use **Chatterbox** only when an authorized external cloned voice or non-presenter narration is required.
3. Cache external narration by normalized text, voice configuration, model revision, and seed.
4. Use **Faster Whisper** only when external transcript timing or captions are requested.
5. Store optional segment and word timestamps for captions and topic-image timing.

Faster Whisper is an alignment and transcript layer; it does not replace Chatterbox.

### 3. Presenter creation

#### Primary: HeyGen

1. Register the channel's authorized presenter reference and consent record.
2. Create or select the corresponding HeyGen avatar.
3. Submit narration or scene text through the official server-side HeyGen API.
4. Poll the asynchronous job, download the resulting MP4, and validate its checksum, duration, resolution, audio, and identity.
5. Feed the clean presenter MP4 into the normal scene compositor.

The HeyGen key must remain server-side in a secret manager or environment variable. It must never appear in the UI, repository, logs, screenshots, or project JSON.

#### Fallback: reusable local motion

1. Register the channel's authorized presenter reference image and consent record.
2. Create a presenter identity/source image with **FLUX.2 Klein 4B Distilled** when generation is needed.
3. Generate several continuous motion clips with **LTX-2.3 Distilled/Flash** or import client-approved clean motion footage.
4. Build a per-presenter motion manifest containing duration, framing, gesture class, intensity, loop safety, checksum, and approval state.
5. Reject clips with frozen endings, discontinuities, face drift, extra fingers, identity drift, or unnatural repetition.
6. Lip-sync selected motion clips locally with **MuseTalk 1.5** for each narration chunk.

The earlier still-image-plus-MuseTalk approach is insufficient: MuseTalk changes mouth/face motion but does not create natural body gestures. LTX remains a **candidate**, not a fully approved solution, because previous samples exhibited stopping/static motion.

### 4. Topic visuals and editorial rendering

- Generate topic imagery with **FLUX.2 Klein 4B Distilled**, supplemented by properly licensed stock or client assets when appropriate.
- Treat the reference YouTube channels as inspiration for cadence and composition, not as assets or branding to copy.
- Add timed images, captions, lower thirds, motion graphics, and simple effects at the scene-rendering layer.
- Use **FFmpeg** filtergraphs for deterministic templates, audio loudness normalization, caption burn-in, compositing, and final assembly.
- Render working intermediates once and perform a single optional final upscale to 4K. Do not advertise native 4K when the source was merely upscaled.

### 5. Application and job control

- **FastAPI** API/control plane.
- **Pydantic** schemas for strict scene, job, asset, consent, and provider contracts.
- **Redis** queue in production; in-memory queue only for local tests.
- Separate **Docker** workers for Chatterbox, FLUX, LTX, MuseTalk, and FFmpeg to isolate conflicting CUDA/Python dependencies.
- Content-addressed caching, bounded retries, idempotency keys, asset lineage, checksums, and per-stage timing/VRAM/cost telemetry.
- Provider interfaces so a compliant external avatar service can be added without changing the scene API.

### 6. GPU and storage lifecycle

The latest storage instruction supersedes the earlier “store every model in R2” plan:

1. Start an ephemeral RunPod GPU worker.
2. Pull code and **pinned, licensed model revisions from Hugging Face** into temporary local storage.
3. Optionally restore a checksum-verified cache from R2 when its license permits redistribution and the cost benefit is demonstrated.
4. Run one heavy model at a time, then release GPU/CPU memory before the next stage.
5. Upload approved outputs, manifests, benchmark reports, logs without secrets, and checksums to private R2.
6. Verify object size and checksum.
7. Download required client deliverables locally.
8. Terminate the pod and delete any temporary/persistent volume created for the job.

An A100 was useful for the proof but is not a per-video requirement. GPU selection should be based on measured VRAM fit, availability, throughput, and total job cost. Do not extrapolate the 12-second proof linearly to a 30–40 minute production estimate.

## Decisions that have been superseded or rejected

| Earlier proposal | Current disposition |
|---|---|
| SadTalker/Wav2Lip as the main presenter stack | Superseded by reusable natural motion plus MuseTalk. |
| MuseTalk applied to one still image | Rejected for insufficient body/head movement. |
| vLLM/paged-attention optimization for FLUX/LTX | Withdrawn; these LLM-specific claims were not technically justified. |
| ComfyUI as the runtime/orchestrator | Not selected; use direct Python APIs/SDKs in isolated workers. |
| Store all model weights permanently on RunPod | Rejected due ongoing storage fees. |
| Store every model in R2 | Superseded by the later instruction to obtain pinned models from Hugging Face inside the container; use R2 selectively. |
| JOGG/DreamFace via Sincronía/DICloak as the primary app path | Client said to forget that app and proceed locally on August 6. |
| HeyGen as a browser-driven, zero-credit workaround | Replaced by the official HeyGen API for any supported production integration. HeyGen remains the preferred primary avatar engine. |
| Browser inspection/credit bypass or watermark removal | Do not implement. It is brittle, insecure, non-scalable, and creates account/terms/legal risk. |
| Mandatory 4K inference | Use optional final upscale after quality approval; native 4K is not required for every intermediate. |

## Current repository alignment

### Implemented or substantially present

- Strict `PRESENTER`, `SPLIT`, and `FULL_VISUAL` schemas and routing.
- FastAPI control-plane structure and provider boundaries.
- FFmpeg scene renderer, captions, assembly, and media validation.
- Chatterbox and MuseTalk local adapters with pinned upstream revisions documented.
- Docker worker definitions for model isolation.
- Queue, retry, caching, cost, consent, storage, and telemetry foundations.
- Official HeyGen API adapter as an optional backend.
- R2/S3 storage utilities and retention tests.
- Motion-library manifest structure and recovered proof assets.

### Not yet proven for production

- A visually approved, realistic local avatar with natural head, shoulder, and hand gestures.
- Reliable LTX motion generation without freezing, drift, or visible repetition.
- Full Chatterbox → Faster Whisper → MuseTalk integration on a production CUDA worker.
- Production Docker builds on the target NVIDIA host.
- A complete, approved 30–40 minute render with measured runtime, VRAM, failure rate, and cost.
- Repeatable multi-channel daily throughput.
- The claimed `$1–$2` cost for a full long-form video.
- Durable production metadata/job recovery beyond the development in-memory path.

## Immediate execution order

1. Rotate any API tokens or credentials that appeared in chat, screenshots, logs, or source history.
2. Lock one authorized presenter reference and a short acceptance rubric.
3. Connect and fund the official HeyGen API account, then verify one short presenter render through the existing adapter.
4. Visually approve identity, gestures, continuity, lip sync, resolution, and watermark-free licensed output.
5. Complete the Chatterbox voice-clone and Faster Whisper word-timing path where external narration is used.
6. Render a 3–5 minute mixed-format quality gate containing all three scene types, topic visuals, captions, text, and motion graphics.
7. Run one resumable 30–40 minute production job and measure HeyGen usage plus all GPU/storage expenses.
8. Retain the local MuseTalk and reusable-motion path as a separately tested fallback.
9. Upload and checksum final deliverables in R2, then pull the client copies locally.
10. Terminate every paid GPU resource after the local stages finish.

## Final recommendation

Proceed with the **official HeyGen API as the primary presenter provider**, while keeping it behind the existing provider interface. Retain the local reusable-motion plus MuseTalk path as the fallback for cost control and provider independence. The next milestone should be approval of a short, licensed HeyGen API sample inside the complete scene pipeline—not a browser workaround and not a full long-form render. Once that quality gate passes, run and measure one resumable 30–40 minute production job.
