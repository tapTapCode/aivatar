# Requirements Alignment Audit

Audit date: 2026-08-15 (Asia/Manila)  
Product scope: Exact Scene AI Video Pipeline (repository root) + `local-ai-video-pipeline-proof/`  
Out of scope: `ClipNET-2-fix/` (separate sports/clip/VOD product)

## Requirement precedence

| Requirement | Source | Date or Recency | Conflicting Requirement | Decision | Reason |
| --- | --- | ---: | --- | --- | --- |
| Immediate target ~10 min ×2 @ 4K delivery (working 720p + labelled upscale) | `local-ai-video-pipeline-proof/PRODUCTION_REQUIREMENTS.md` | 2026-08-03 | Original brief 20–30 min videos | Prefer 10-min MVP target; treat 30-min as future scale | Newest authoritative production doc |
| Avatar: JOGG / DreamFace external first; MuseTalk local fallback; HeyGen later | Same | 2026-08-03 | Root stack treats MuseTalk/FLUX/LTX workers as primary path | Prefer provider-agnostic import + local fallback | Newest avatar policy |
| Cloudflare R2 durable store; ephemeral GPU disks | Same + proof README R2 section | 2026-08 | Root defaults to in-memory metadata + local files | Prefer R2 for production path; keep local for mock/dev | Newest storage lifecycle |
| Cost ≈ $1–$2 per completed video | Original product baseline | Older | Cost preflight forbids promising $1–$2 for 10-min without fresh benchmark | Do not claim met | Evidence in `reports/cost_breakdown.md` |
| Operator UI / runnable without developer | PRODUCTION_REQUIREMENTS §1 | 2026-08-03 | Proof README “no dashboard” framing | Build operator UI against Exact Scene API | Newest ops need wins over proof-only framing |
| Exact PRESENTER / SPLIT / FULL_VISUAL scene contracts | Root README + `docs/architecture.md` | 2026-07-15 | Faceless marketing feature laundry list | Keep exact scene contracts | Implemented and tested; still compatible with documentary flow |
| ClipNET web app as product UI | `ClipNET-2-fix/` | Parallel product | Long-form documentary platform | Exclude from scoring | Different product domain |

## Alignment matrix

Completion Weight is the contribution of that row toward its area (0–1). Priority: P0 / P1 / P2 / P3.

| Area | Requirement | Source | Current Evidence | Status | Completion Weight | Priority | Next Action |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| Foundation | Auth API key + owner header | `src/api/security.py` + `src/auth/` | Database sessions, CSRF, register/login; SSO/Resend secrets missing | Partially complete | 0.7 | P1 | Configure Resend + OAuth secrets |
| Foundation | Project create | `POST /v1/projects` | Implemented; always stored as draft | Complete | 0.9 | P1 | Keep list/edit UX current |
| Foundation | Channel templates | `templates/*.yaml` | default + two reference templates | Partially complete | 0.6 | P1 | Multi-channel operator config |
| Foundation | Language management | Original brief | Not implemented | Missing | 0 | P2 | Defer |
| Foundation | Provider configuration | env + worker URLs | Mock vs workers switch | Partially complete | 0.5 | P1 | Document + UI provider mode |
| Foundation | Asset provenance | `GeneratedAsset` schema | Implemented in mock path | Complete but untested on GPU | 0.7 | P1 | Persist to R2 |
| Workflow | Topic / brief / research / outline | Original brief | Not in newest PRODUCTION_REQUIREMENTS | Out of current MVP scope | 0 | P3 | Defer LLM research |
| Workflow | Script as ProjectScript scenes | Root schemas | Strict Pydantic scenes; studio + projects editor | Complete but untested long-form | 0.8 | P1 | Ten-minute scene packs |
| Workflow | Script approval gate | Original + PRODUCTION_REQUIREMENTS avatar gate | `approval_state` + `/approve`; renders require approved script | Partially complete | 0.7 | P1 | Keep avatar quality gate separate |
| Workflow | Voiceover (TTS) | Chatterbox / speech provider | Mock verified; real on RunPod 12s proof | Partially complete | 0.55 | P0 | Wire production TTS via R2 bootstrap |
| Workflow | Avatar generation | JOGG/DreamFace/MuseTalk | Import contract started in proof; MuseTalk in root | Partially complete | 0.35 | P0 | JOGG vs DreamFace comparison gate |
| Workflow | Scene planning | Scene schema + routing | Implemented | Complete but untested long-form | 0.7 | P1 | Ten-minute scene packs |
| Workflow | B-roll / stock matching | Original brief | Visual provider exists; no stock search | Missing | 0 | P2 | Optional stock provider |
| Workflow | Split-screen | SPLIT format | Implemented + mock demo | Complete but untested GPU | 0.75 | P1 | Real visual worker |
| Workflow | Subtitles | captions renderer | Implemented | Complete but untested long-form | 0.7 | P1 | Validate on 10-min |
| Workflow | Video assembly | FFmpeg assembler | Mock + 12s proof | Partially complete | 0.6 | P0 | Resumable 10-min assembly |
| Workflow | Thumbnail / YT metadata | Original brief | Missing | Missing | 0 | P2 | Post-MVP |
| Workflow | Quality review UI | PRODUCTION_REQUIREMENTS | Manual only | Missing | 0 | P1 | Review stage in operator UI |
| Workflow | Google Drive / YouTube | Original brief | Missing | Missing | 0 | P2 | After MVP render |
| Operations | Queue | memory + Redis impl | Neon claim/recovery on list/get | Partially complete | 0.7 | P1 | Redis fan-out if multi-instance |
| Operations | Job progress / cancel | JobState + cancel API | Neon persist + list/get recovery | Complete | 0.85 | P1 | Stage resume |
| Operations | Retry / idempotency | retry + Idempotency-Key | Implemented | Partially complete | 0.6 | P1 | Stage-level resume DB |
| Operations | Cost tracking | orchestration/cost + metrics | Partial counters; no per-video ledger | Partially complete | 0.35 | P1 | Stage cost records |
| Operations | R2 storage | proof `r2_storage.py` | Avatar package + MD5 restore manifest 2026-08-15 | Partially complete | 0.75 | P1 | Add Flux/LTX package |
| Operations | RunPod volume migration | PRODUCTION_REQUIREMENTS §6 | Inventory: 0 volumes | Complete and verified | 1.0 | — | Closed |
| UI/UX | Application shell / nav | This audit | Next.js workspace on staging | Complete | 0.9 | P1 | Keep responsive/a11y current |
| UI/UX | Dashboard / queue / cost pages | This audit | Overview, studio, projects, videos, settings | Partially complete | 0.8 | P1 | Stage cost ledger UI |
| Testing | Unit/contract tests | `tests/` | Present; media-marked | Partially complete | 0.6 | P1 | Expand E2E |
| Testing | GPU/long-form benchmarks | reports | 12s only | Partially complete | 0.25 | P0 | Fresh 10-min benchmark |
| Deploy | Docker Compose | docker* | Manifests; Docker often unavailable | Partially complete | 0.4 | P2 | Verify builds |
| Deploy | Docs | docs/* | Strong for control plane | Complete but untested ops | 0.7 | P2 | Keep current |

## Summary judgment

The codebase is **partially aligned** with the newest production requirements: the Exact Scene control plane, Next.js operator workspace, and FFmpeg contracts are real and tested on mocks; script renders now require an explicit approval. The proof pipeline adds R2/RunPod ops and a clearer 10-minute documentary target. It is **not aligned** with the full original platform brief (research, Drive, YouTube publish, multi-language) because those items are either superseded or not yet built.

ClipNET is intentionally excluded and must not inflate completion percentage.
