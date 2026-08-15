# Aivatar QA Release Report

**Date:** 2026-08-15  
**Target:** https://aivatar-staging.vercel.app (UI) → https://aivatar-api-staging.vercel.app (API)  
**Auditor role:** Senior QA / architecture / browser / security / release  
**Browser:** Cursor built-in browser (view `fbf0d5`)  
**Verdict:** **CONDITIONALLY READY**

This is a private team studio, not a public website. “Ready” for this product means a shared MP4 the team can use. This report separates **application-code defects** from **environment blockers** and from **unverified authenticated journeys**.

---

## Executive summary

| Area | Result |
| --- | --- |
| Overall result | **CONDITIONALLY READY** for private-team UAT. **Not** a clean production-release sign-off. |
| Application health | Staging UI and API boot. `/health` is `ok`. Default provider is `heygen_api`. Live alias reports HeyGen configured. `/ready` is 503 on Vercel because ffmpeg is absent — expected, and the HeyGen PRESENTER path does not need ffmpeg. |
| Architecture health | **Good.** Studio → API → provider factory → HeyGen client is a real boundary. Approval and job state are server-authoritative. `Dashboard.tsx` is a maintainability risk (~1,100 lines). |
| Connectivity health | Core HeyGen workflow is **FULLY CONNECTED in code and automated tests**. Live logged-in Studio → generate → download was **not** exercised in the browser. |
| Browser test result | Public auth surfaces **PASS**. Authenticated workspace **BLOCKED** (session required; password fill / account creation were not executed). |
| Automated-test result | Frontend Vitest **17 passed**. Typecheck **passed**. Backend targeted suite **34 passed** (HeyGen workflow/default/cost/provider, script approval, auth, API). Full pytest, ESLint, and `next build` were not run in this pass. |
| HeyGen readiness | **Code path ready.** Live staging alias has a server-side key (`heygen_configured=true`, catalog reachable). Preview still lacks `HEYGEN_API_KEY`. No paid live generate was run. |
| Release recommendation | Start private UAT with a known team account. Deploy the duplicate-generate guard before anyone hammers Approve. Do not treat the status board’s “100%” as evidence. |

---

## Release verdict

```text
CONDITIONALLY READY
```

UAT may start for authorized teammates **if** they accept these conditions:

1. Logged-in Studio, generation, polling, recovery, playback, and download were **not** browser-verified in this session.
2. The duplicate-generate client lock exists in the working tree and is covered by a Vitest, but it is **not on the live staging alias** until the frontend is redeployed.
3. Do **not** fire repeated live HeyGen renders for coverage. One controlled generate per channel is enough.
4. The Cursor status board is **manually maintained**. Several “100%” cells overstate browser/UAT completeness.
5. The git working tree on `master` has **no commits**. The entire application is untracked. That is a release-process gap, not a runtime defect.

Choose **NOT READY FOR RELEASE** if the bar is “public production with a completed logged-in browser UAT.” That bar was not met.

---

## Phase 1 — Git state

Inspected before changes.

| Item | Value |
| --- | --- |
| Branch | `master` |
| Latest commit | None — repository has no commits |
| Staged | None observed |
| Working tree | Entire application untracked (`src/`, `frontend/`, `docs/`, artifacts) |
| This session | Did **not** commit, reset, force-push, or rewrite history |

Do not treat the tree as a releasable git revision until someone creates an intentional first commit.

---

## Architecture map

Traced from imports and runtime paths, not names.

| Layer | Actual stack |
| --- | --- |
| Frontend | Next.js **16.3.1** App Router, React **19.2.8** |
| UI routing | Single page `frontend/app/page.tsx` → `AppRoot` → `AuthScreen` or `Dashboard`. Client state routes: `overview`, `studio`, `projects`, `assets`, `templates`, `tools`, `videos`, `settings` |
| OAuth proxy | `frontend/app/v1/auth/oauth/{google,apple}[/callback]/route.ts` → FastAPI |
| API | FastAPI `src/api/main.py` via `api/index.py` on Vercel |
| Rewrites | `/v1`, `/health`, `/ready`, `/metrics` → `FASTAPI_ORIGIN` |
| Auth | Cookie session + CSRF. Staging `AUTH_REQUIRED=true`. `owner_id` = session user id. `X-Owner-Id` only when auth is off or a valid `X-API-Key` is presented |
| Persistence | Neon/Postgres when `DATABASE_URL` is set; tests use memory. Jobs unique on `(owner_id, idempotency_key)` |
| Avatar provider | `build_provider_set` / `lipsync_mode()` → `HeyGenLipSyncGenerator` when `AVATAR_VIDEO_PROVIDER=heygen_api` (default in `src/api/config.py`) |
| MuseTalk | Seeded only for `local_musetalk`. Not the default path |
| Job recovery | `GET /v1/videos/{id}` resumes in-flight HeyGen jobs via `provider_ref` without a local FFmpeg render |
| Polling | UI `setInterval(loadWorkspace, 4000)` while any job is non-terminal. Backend HeyGen poll interval default **10s**, timeout **7200s** |
| Cost | Backend `heygen_rate_usd_per_minute` (default **4.0**). `heygen_avatar_iv_cost(seconds / 60 * rate)` |
| Storage | Local or R2. Completed MP4 retained under owner/project/video |
| Tests | Pytest + Vitest. No Playwright/e2e package in `frontend/package.json` |

Client/server boundary: the browser never calls `api.heygen.com`. The HeyGen key is server-only (`heygen_api_key`, not `NEXT_PUBLIC_*`).

---

## Feature inventory

Only features that exist in this repository.

| Feature | Route | UI | Backend | Persistence | External provider | Auth required |
| --- | --- | --- | --- | --- | --- | --- |
| Landing / sign-in | `/` | `AuthScreen` | `/v1/auth/*` | Auth DB | Google OAuth (Apple paused) | Public |
| Register | `/` view register | Yes | `POST /v1/auth/register` | Auth DB | Resend if configured | Public |
| Password reset | `/` view forgot/reset | Yes | forgot/reset endpoints | Auth DB | Resend if configured | Public |
| Email verify | `/` view verify | Yes | verify endpoint | Auth DB | Email | Token |
| Dashboard / Home | client `overview` | Yes | `loadWorkspace` fan-out | DB | None | Yes |
| Studio | client `studio` | Yes | projects + videos + heygen-avatars | DB | HeyGen | Yes |
| Projects | client `projects` | Yes | CRUD + approve | DB | None | Yes |
| Script review dialog | Projects | Yes | replace + approve + create video | DB | HeyGen on approve | Yes |
| Assets / avatar register | client `assets` | Yes | `POST /v1/heygen-avatars`, media | DB | HeyGen catalog | Yes |
| Templates | client `templates` | Yes | Opens Studio presets | None | None | Yes |
| Tools | client `tools` | Cards → Studio | None | None | None | Yes |
| Videos / playback / download | client `videos` | Yes | `/v1/videos`, `/v1/assets/.../content` | DB + storage | HeyGen / storage | Yes |
| Settings / profile / cost | client `settings` | Yes | auth profile + `/v1/costs` + health | DB | None | Yes |
| Command palette | Ctrl/Cmd+K | Yes | Client navigation | None | None | Yes |
| Health | `/health` | Settings stats | FastAPI | None | HeyGen flag only | Public |
| Readiness | `/ready` | Settings “Runtime” | FastAPI | None | ffmpeg/ffprobe | Public |
| Metrics | `/metrics` | Footer hint | FastAPI | Queue depth | None | Session |
| Status board | Cursor canvas | Manual todos | None | None | None | N/A |

No separate public marketing site, billing portal, admin console, or support desk exists.

---

## Route inventory

| Route | Class | Purpose | Auth | Important interactions | Browser tested |
| --- | --- | --- | --- | --- | --- |
| `/` | PUBLIC / AUTHENTICATED | Auth or workspace | Session | Email, SSO, register, reset | **Yes** (logged-out) |
| `/?view=register` | PUBLIC | Create account | Public | Form only; not submitted | **Yes** (view) |
| `/?view=forgot` | PUBLIC | Reset request | Public | Form opened; not submitted | **Yes** |
| `/?error=oauth_*` | PUBLIC | SSO error | Public | Status notice | **Yes** |
| `/v1/auth/oauth/google` | CALLBACK | Google start | Public | Not followed (third party) | Code + config only |
| `/v1/auth/oauth/apple` | CALLBACK | Apple start | Public | UI gated to `#`; direct URL 503→generic error | **Partial** |
| `/v1/auth/oauth/*/callback` | CALLBACK | OAuth finish | Public | Not live-tested | Code only |
| `/health` | HEALTH | Provider + key flags | Public | Boolean flags only | **Yes** (no secrets) |
| `/ready` | HEALTH | ffmpeg/store | Public | 503 on Vercel | Code + prior ops |
| `/metrics` | HEALTH | Prometheus text | Session | Not opened as a page | Code only |
| `/v1/projects*` | API | Draft/approve/list | Session + CSRF | Not browser-tested logged-in | Code + tests |
| `/v1/videos*` | API | Create/poll/cancel/retry | Session + CSRF | Not live-generated | Code + tests |
| `/v1/heygen/catalog` | API | Voices/avatars | Session | Live catalog when key present | Code + curl prior |
| `/v1/heygen-avatars` | API | Register avatar ID | Session + rights header | Not browser-tested | Code + tests |
| `/v1/media*` | API | Media registry | Session | Not browser-tested | Code + ownership test |
| `/v1/costs` | API | Ledger | Session | Not browser-tested | Code + tests |
| `/v1/assets*` | API | Metadata + download | Session | Not browser-tested | Code only |
| `/v1/internal/modal-jobs/{id}` | INTERNAL | Signed worker updates | HMAC | Never in UI | Code only |
| unknown path | ERROR | Next.js default 404 | Public | No home link | **Yes** |

**Orphaned UI routes:** none. All Dashboard sections are reachable from the sidebar once authenticated.  
**Orphaned API:** `/v1/jobs/{job_id}` exists beside `/v1/videos/{video_id}`; the UI uses videos. Not disconnected — alternate read path.

Client routes (`studio`, `projects`, …) are **not** Next.js paths. Direct URL `/studio` is a 404. That is expected and should stay documented for UAT testers.

---

## Feature connectivity matrix

| Feature | UI | Backend | Persistence | Provider | Browser | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Authentication | Yes | Yes | Auth DB | Google / email | Logged-out **PASS**; login **BLOCKED** | **PARTIALLY CONNECTED** |
| Registration | Yes | Yes | Auth DB | Email | View **PASS**; submit not run | **PARTIALLY CONNECTED** |
| Projects | Yes | Yes | DB | N/A | Not logged in | **FULLY CONNECTED** (code) / browser **BLOCKED** |
| Avatar registration | Yes | Yes | Media registry | HeyGen | Not logged in | **FULLY CONNECTED** (code) / browser **BLOCKED** |
| Script approval | Yes | Yes — stored `approval_state` | DB | N/A | Not logged in | **FULLY CONNECTED** (code) / browser **BLOCKED** |
| Video generation | Yes | Yes — approve + idempotency | Job row | HeyGen | No paid live generate | **FULLY CONNECTED** (code) / live **NOT TESTED** |
| Job polling | Yes — 4s workspace refresh | Resume on `GET /v1/videos/{id}` | Job + `provider_ref` | HeyGen | Not logged in | **FULLY CONNECTED** (code) / browser **BLOCKED** |
| Job recovery | Reload uses persisted jobs | Resume execute | DB | HeyGen | Not logged in | **FULLY CONNECTED** (code) / browser **BLOCKED** |
| Video playback | Videos view | Asset content | Storage | Storage/HeyGen | Not logged in | **FULLY CONNECTED** (code) / browser **BLOCKED** |
| Download | Videos view | Asset content | Storage | Storage | Not logged in | **FULLY CONNECTED** (code) / browser **BLOCKED** |
| Cost tracking | Settings | `/v1/costs` + health rate | Job costs | N/A | Health rate **PASS** (`4`) | **FULLY CONNECTED** (code) / UI **BLOCKED** |
| Health | Settings + `/health` | FastAPI | N/A | HeyGen flag | **PASS** | **FULLY CONNECTED** |
| Apple SSO | Visible, paused | 503 when disabled | N/A | Apple | UI gate **PASS** | **PARTIALLY CONNECTED** |
| Keep me signed in | Checkbox | Server TTL only | Cookie | N/A | Unwired | **DISCONNECTED** (decorative) |

A feature blocked only by missing login is not marked `PASS`.

---

## HeyGen integration report

```text
Provider abstraction:     Yes — lipsync_mode() / build_provider_set() / HeyGenLipSyncGenerator
Default provider:         heygen_api (src/api/config.py). Live /health confirms it.
Avatar registration:      POST /v1/heygen-avatars stores a presenter media row (ID, not a still)
Generation:               POST /v1/videos after server-side approved fingerprint match
Persistence:              JobRecord + provider_ref (HeyGen video id)
Polling:                  UI 4s full workspace; GET /v1/videos/{id} resumes HeyGen poll
Recovery:                 Reload re-fetches jobs; resume does not create a second HeyGen job if provider_ref exists (covered by tests)
Download:                 generator.download_completed → asset store / optional R2
Cost calculation:         seconds/60 * heygen_rate_usd_per_minute; default $4; cap heygen_maximum_cost_usd_per_job ($25)
Missing-key behavior:     App boots. Catalog empty. Health heygen_configured=false. Generate must not fake an MP4 (tests cover empty catalog / require key at generate time)
Preview configuration:    Preview still lacks HEYGEN_API_KEY (environment). Live staging alias currently has the key.
Live verification:        Health + catalog flags only. No paid create_presenter_video from this QA session.
```

Studio does **not** `fetch("https://api.heygen...")`. That boundary is intact. Do not invent a second abstraction.

### Duplicate paid generation

**Before this session:** `Studio.submit` set `busy` only after validation/register. `createVideo` minted a new `crypto.randomUUID()` idempotency key per call. A double click before the re-render could enqueue two HeyGen jobs. Server idempotency does not help when keys differ.

**Fix in this session:** synchronous `submitting` ref + `beginWork()`/`endWork()` around the whole Studio submit and Script Review approve path. Register-from-submit no longer drops the lock between register and create.

**Still true after the fix:** a second *intentional* generate (new click after the first job finishes) still uses a new UUID. That is correct. There is still **no server-side “one in-flight job per project”** guard. Add that later if UAT shows retries creating extras.

### Polling

| Active jobs | What happens |
| --- | --- |
| 1 | One browser calls `loadWorkspace` every 4s → 7 parallel API calls (`/health`, `/ready`, projects, videos, metrics, media, costs) |
| 10 | Same, if they share one browser session |
| 100–1,000 | Each open browser independently hammers the API. The API then may resume HeyGen polls. This does **not** scale to 100k users. Fine for a small team. |

HeyGen status polling from the server uses `heygen_poll_interval_seconds` (10s) and stops on completion/timeout. The UI does **not** poll HeyGen directly.

---

## Environment blockers vs application bugs

### ENVIRONMENT CONFIGURATION BLOCKER

```text
HeyGen live Preview generation:
BLOCKED BY ENVIRONMENT

Reason:
Required server-side HeyGen credential is not configured on Vercel Preview.
Empty key does not fail boot. That is correct application behavior.
```

```text
Logged-in Cursor browser UAT of Studio / generate / download:
BLOCKED BY SESSION

Reason:
Staging requires authentication. This session did not submit a password or create an account.
Unauthenticated API probes correctly return 401.
```

```text
Live paid HeyGen MP4:
NOT TESTED

Reason:
Avoid unnecessary paid renders. Code path is covered by mocked provider tests.
```

Live **staging alias** `/health` in this session:

- `status=ok`
- `avatar_video_provider=heygen_api`
- `heygen_configured=true`
- `cost_billing=heygen_api`
- `heygen_engine=avatar_iv`
- `heygen_rate_usd_per_minute=4`

That contradicts the status-board line “HEYGEN_API_KEY still missing” **for the aliased staging URL**. The note remains accurate for **Preview** deploys.

### APPLICATION BUG / GAP (this session)

See Bugs below. Confirmed low-risk fixes are listed under Refactors.

---

## Architecture health

| Category | Rating | Findings |
| --- | --- | --- |
| Code connectivity | **Good** | Register → approve → enqueue → persist → resume → MP4 is wired. UI does not own business state. |
| Maintainability | **Needs work** | `Dashboard.tsx` is a god component (Studio, Projects, Assets, Videos, Settings, ScriptReviewDialog). |
| Efficiency | **Needs work** | 4s full-workspace poll; `/v1/videos` and `/v1/costs` list all owner jobs with no pagination. |
| Scalability | **Needs work** | Client-driven poll fan-out; unbounded job lists; per-browser hammers. Acceptable for <10 concurrent editors. |
| Security | **Good** | Session + CSRF + origin on mutations. Owner scoping on projects/jobs/media. HeyGen key server-only. Internal worker route HMAC-signed. |
| Reliability | **Good** | Job resume via `provider_ref`. Approval fingerprint conflict (409). Cost cap before HeyGen create. |
| Type safety | **Good** | No `any` / `@ts-ignore` in `frontend/`. Pydantic on API. HeyGen payloads still need runtime caution (dict `.get`). |
| Validation | **Good** | Avatar ID, approval fingerprint, idempotency header length, consent when `provider_mode=workers`. |
| Testability | **Good** | FastAPI TestClient + Vitest cover the HeyGen default path. No browser e2e suite. |
| Observability | **Needs work** | `/metrics` exists. Little structured product telemetry for generate failures. FastAPI deprecation warnings on Python 3.14. |

---

## Efficiency / scalability / maintainability

**Frontend**

- `loadWorkspace` always fans out seven requests, including `/ready` (503 on Vercel, swallowed to `not-ready`).
- Polling repeats that fan-out every 4s whenever any job is in-flight.
- Almost the entire workspace is one client component.

**Backend**

- `list_jobs` / `get_costs` are unbounded per owner.
- `GET /v1/videos` also kicks `consume_one_job` as a background task — extra work on every list.
- HeyGen create is not repeated on resume when `provider_ref` is set (tested).

**Database**

- Ownership filters exist.
- Unique `(owner_id, idempotency_key)` is the right constraint.
- No pagination on project/job lists. Do not add indexes blindly; add pagination before 1,000-job owners.

**Maintainability**

- HeyGen is not copied through JSX. Keep it that way.
- Cost rate has a single backend source of truth. UI displays health/ledger values.
- Approval source of truth is the stored project, not React state. `POST /v1/videos` rejects draft / fingerprint mismatch.
- Job source of truth is the DB row, reconciled with HeyGen via `provider_ref`.
- Status board “100%” values are **not** computed from CI.

**Dead / leftover**

- MuseTalk seed is gated. Packaged presenter is not created on the HeyGen path (tested).
- `local-ai-video-pipeline-proof/` is a sibling proof tree, not the Studio path.
- Input `placeholder` strings are UX hints, not stub implementations.
- No `TODO` / `FIXME` / `NotImplemented` in `src/`.

---

## Security / authorization

| Check | Result |
| --- | --- |
| Unauthenticated `/v1/auth/session` | 401 |
| Unauthenticated `/v1/projects` | 401 `authentication required` |
| Invalid login | 401 `invalid email or password` (API probe; no password logged) |
| CSRF on mutations | Required when session auth is on |
| Owner scoping | `get_project` / `get_video_job` / media list take `owner_id`. Media list test uses a second owner |
| `X-Owner-Id` spoofing | Ignored unless API key present or `AUTH_REQUIRED=false` |
| HeyGen key in client bundle | Not `NEXT_PUBLIC_*` |
| Worker callback | `X-Aivatar-Signature` |
| Secrets in this report | None printed |

Cross-user IDOR was **not** browser-tested with two live accounts. Server tests and owner filters are the current evidence.

---

## Automated tests

| Suite | Command | Result |
| --- | --- | --- |
| Frontend unit | `cd frontend && npm test` | **17 passed** (5 files), including new double-generate guard |
| Frontend types | `cd frontend && npm run typecheck` | **passed** |
| Backend HeyGen / approval / provider | `.venv/bin/pytest` targeted files | **19 passed** |
| Backend auth + API | `tests/test_auth.py tests/test_api.py` | **15 passed** |
| ESLint | `npm run lint` | Not run this pass |
| `next build` | `npm run build` | Not run this pass |
| Full pytest | `pytest` | Not run this pass |
| Playwright | Not in package.json | N/A |

Passing tests do **not** replace logged-in browser UAT.

---

## Browser coverage

Public surfaces on https://aivatar-staging.vercel.app.

| Route | Loaded | Controls tested | Console | Network | Status |
| --- | --- | --- | --- | --- | --- |
| `/` login email | Yes | Email, password (empty), Keep me signed in (visual), Forgot password, Sign in (empty), Create account (view), tabs | No page crash | Session 401 expected | **PASS** |
| `/` login SSO | Yes | Use SSO, Google (not followed), Apple (paused) | Notice shown | — | **PASS** |
| `/` register view | Yes | Empty Create account → focused Full name | — | Not submitted | **PASS** |
| `/` forgot password | Yes | Open form, Back to sign in | — | Reset not sent | **PASS** |
| `/?error=oauth_failed&method=sso` | Yes | Status: “Google or Apple could not verify this account.” | — | — | **PASS** |
| Apple paused click | Yes | Notice: “Apple sign-in is paused…” | — | `href="#"` | **PASS** |
| `/this-route-does-not-exist` | Yes | Default Next 404 | — | — | **EXPECTED BEHAVIOR** (no branded home link) |
| `/health` via page fetch | Yes | Flags only | — | 200 | **PASS** |
| `/studio` etc. | 404 | N/A | — | — | **EXPECTED BEHAVIOR** (client routes) |
| Overview / Studio / Projects / Assets / Videos / Settings | Not reached | — | — | 401 without session | **BLOCKED** |

### Responsive

Auth layout stacks at `max-width: 860px`. Workspace sidebar becomes a drawer at `740px`.

| Size | Overflow-X | Notes | Status |
| --- | --- | --- | --- |
| 375 × 812 | None | SSO/email controls reachable; marketing card hidden as designed | **PASS** |
| 768 × 1024 | None | Stacked auth | **PASS** |
| 1280 × 800 | None | Two-column auth | **PASS** |
| 1440 × 900 | Metrics set | Same split layout | **PASS** |
| 430 × 932 | CSS path only | Shares 480px rules | **PASS** (code + 375 evidence) |

Authenticated Studio/dashboard responsive QA is **BLOCKED**.

### Accessibility

| Check | Result |
| --- | --- |
| Skip link | Present (`Skip to content`) |
| Auth tabs | `role="tab"` / `aria-selected` |
| Required fields | HTML5 `required`; empty Sign in / Create account move focus to the first invalid field |
| Apple paused | `aria-disabled` + `href="#"` + click notice |
| OAuth error | `role="status"` `aria-live="polite"` |
| Focus ring | Inputs have focus styles. OAuth/tab/submit rings were weak; **added** `:focus-visible` in this session |
| Keep me signed in | Exposed as checkbox but **readonly / unwired** |
| Keyboard | Tab reaches SSO controls. Full workspace keyboard pass **BLOCKED** |
| Heading structure | Auth: h1 marketing + h2 form. Acceptable |

---

## Interactive control inventory (public)

Exercised or explicitly skipped:

| Control | Action | Result | Status |
| --- | --- | --- | --- |
| Use email / Use SSO | Click | Tabs switch | **PASS** |
| Email / Password | Empty Sign in | Focus email (required) | **PASS** |
| Keep me signed in | Visible, checked | No `name`; does not change TTL | **EXPECTED BEHAVIOR** / P3 |
| Forgot password | Open + Back | Form works | **PASS** |
| Send reset link | Not submitted | Avoid email side effects | **NOT APPLICABLE** |
| Sign in with credentials | Not filled | Classifier / no QA password | **BLOCKED** |
| Create an account (view) | Open | Register form | **PASS** |
| Create account (submit) | Empty only | Focus Full name | **PASS** |
| Continue with Google | Not followed | Would leave to Google | **NOT APPLICABLE** |
| Continue with Apple | Click | Paused notice; no navigation | **PASS** |
| Aivatar logo link | Present | `/` | Visual only |

---

## Status board accuracy

The Cursor canvas “7 of 7 Done” board is **manual documentation**, not a computed score.

| Board claim | Reality |
| --- | --- |
| Default provider heygen_api; MuseTalk seed off | **True** (config + tests + live health) |
| Register → approve → HeyGen MP4 | **True in code/tests.** Not browser-verified logged-in |
| Vercel resumes HeyGen without local FFmpeg | **True in code** (`provider_ref` resume) |
| Studio asks for HeyGen avatar ID | **True** (UI copy + Vitest) |
| Avatar IV at configured per-minute rate | **True** (default $4; live health `rate=4`) |
| Backend + UI tests cover HeyGen default path | **True** |
| Staging health is heygen_api; `HEYGEN_API_KEY` still missing | **Half true.** Health is `heygen_api`. Live alias is **configured**. Preview is still missing the key |
| Implicit “100% complete” | **False** as a release metric. Files and tests exist. Logged-in browser UAT does not |

---

## Bugs

### QA-001 — Double-click can enqueue two paid HeyGen jobs

**Severity:** P1  
**Feature:** Video generation  
**Route:** Studio / Script review  
**Status:** **FIXED in working tree** (not on live staging until frontend deploy)

#### Reproduction

1. Open Studio with rights checked and a HeyGen avatar selected.
2. Double-activate “Approve and generate” before React re-renders `busy`.

#### Expected

One `POST /v1/videos` and one HeyGen create.

#### Actual

`busy` was set after awaits; each click minted a new idempotency key.

#### Root cause

Client lock was state-only and started too late. Server idempotency is per key, not per project.

#### Recommended fix

Shipped: `submitting` ref around the full submit. Follow-up: reject a new create while the same project already has a non-terminal job.

---

### QA-002 — Success toasts cleared by workspace refresh

**Severity:** P3  
**Feature:** Studio alerts  
**Route:** Workspace shell  
**Status:** **FIXED in working tree**

`refresh()` cleared every alert. Generate called `showAlert` then `refresh()`, so “Queued …” never stayed visible. In-progress polling (4s) would also wipe toasts.

Fix: successful refresh preserves `kind === "ok"` alerts.

---

### QA-003 — “Keep me signed in” is decorative

**Severity:** P3  
**Feature:** Authentication  
**Route:** `/`  
**Status:** Open

Checkbox has no `name` and is a11y-readonly. Session TTL is `session_ttl_hours` on the server only.

#### Recommended fix

Wire it to a documented TTL **or** remove/disable it and say the session length is set by the server.

---

### QA-004 — Disabled Apple start URL returns a generic OAuth failure

**Severity:** P3  
**Feature:** Apple SSO  
**Route:** `/v1/auth/oauth/apple`  
**Status:** **FIXED in working tree** (not on live alias)

Backend already returns 503 “Apple sign-in is paused.” The Next proxy mapped every 503 to `/?error=oauth_failed`. UI copy then said the account could not be verified.

Fix: 503 → `oauth_paused` + dedicated notice. Live alias still has the old proxy until redeploy. The on-page Apple button already uses `href="#"` and the correct paused notice.

---

### QA-005 — Default Next.js 404 has no way home

**Severity:** P4  
**Feature:** Error  
**Route:** unknown paths  
**Status:** Open

`/this-route-does-not-exist` shows the stock “404 / This page could not be found.” No branded back link. Acceptable for a private studio; add `not-found.tsx` if UAT wants it.

---

### QA-006 — Authenticated browser journeys unverified

**Severity:** P1 (release evidence gap, not a proven product break)  
**Feature:** Studio / generation / download  
**Route:** client workspace  
**Status:** Open — needs a teammate session

Without a logged-in Cursor browser pass, do not claim the primary workflow is production-verified.

---

## Refactors completed

### 1. Duplicate-generate lock

- **Problem:** Two rapid Approve clicks could create two paid HeyGen jobs.
- **Root cause:** `busy` was set after awaits; idempotency keys were random per call.
- **Files:** `frontend/components/Dashboard.tsx`, `frontend/components/Dashboard.test.tsx`
- **Solution:** Synchronous submit lock for Studio and Script Review; register-during-submit no longer releases the lock early.
- **Why necessary:** Paid-provider safety (priority 6).
- **Tests:** Vitest “does not enqueue two HeyGen jobs on a double generate click” — **passed**.
- **Browser verification:** Not deployable on staging in this session.
- **Regression:** Existing HeyGen catalog → approve Vitest still **passed**.

### 2. Preserve success alerts across refresh

- **Problem:** Queue toasts vanished immediately; polling wiped them.
- **Root cause:** `refresh()` reset all alerts.
- **Files:** `frontend/components/Dashboard.tsx`
- **Solution:** Keep `ok` alerts after a successful reload.
- **Tests:** Covered indirectly by the generate-path tests; no toast assertion (refresh used to erase it).
- **Browser verification:** Code-level only.

### 3. Paused Apple SSO error code

- **Problem:** Direct Apple start looked like a failed verification.
- **Root cause:** Proxy treated 503 as `oauth_failed`.
- **Files:** `frontend/lib/oauth-proxy.ts`, `frontend/components/AuthScreen.tsx`
- **Solution:** `oauth_paused` mapping + copy.
- **Tests:** Existing oauth-proxy location tests still apply. Live alias not redeployed.
- **Browser verification:** On-page Apple button already showed the paused notice (**PASS**).

### 4. Auth focus rings

- **Problem:** Tab to Apple/Google showed `outline: none`.
- **Files:** `frontend/app/globals.css`
- **Solution:** `:focus-visible` on oauth buttons, auth tabs, submit, and view links.
- **Browser verification:** CSS only; not redeployed.

---

## Final release checklist

- [x] Repository fully scanned
- [x] Git state understood
- [x] Architecture mapped
- [x] Features inventoried
- [x] Routes inventoried
- [x] Frontend/backend connectivity traced
- [x] Database connectivity traced
- [x] HeyGen integration traced
- [x] Authentication tested (logged-out + API; login blocked)
- [x] Authorization tested (API/tests; not two-account browser IDOR)
- [ ] Avatar registration tested in browser (code + tests only)
- [ ] Script approval tested in browser (code + tests only)
- [x] Generation tested or correctly environment-blocked (code connected; live paid generate not run)
- [x] Duplicate-generation risk checked (fixed in tree)
- [x] Job persistence checked (code + tests)
- [x] Polling checked (code audit)
- [x] Recovery checked (code + tests)
- [ ] Video playback checked in browser
- [ ] Download checked in browser
- [x] Cost calculation checked (backend + live health rate)
- [x] Missing-key behavior checked (tests + Preview noted)
- [x] Every meaningful **public** button exercised
- [x] Console inspected on public pages (no crash / no secret leak)
- [x] Network inspected for health/auth (no secrets recorded)
- [x] Responsive QA completed for **auth**
- [x] Accessibility QA completed for **auth**
- [x] Efficiency audited
- [x] Scalability audited
- [x] Maintainability audited
- [x] Security audited
- [x] Type safety audited
- [x] Automated tests run (targeted)
- [x] Confirmed defects fixed where safe
- [x] Regression tests completed for the generate lock
- [ ] Final logged-in browser regression
- [x] Environment blockers documented
- [x] `QA_RELEASE_REPORT.md` completed
- [x] Release verdict supported by evidence

---

## What UAT should do next

1. Redeploy **frontend** so the generate lock, toast fix, and `oauth_paused` mapping are on the alias.
2. Sign in with a real team account in Cursor’s browser (do not bypass auth).
3. Create `QA Project — 2026-08-15`, register the **channel’s authorized** HeyGen avatar ID (do not clone a third-party face).
4. Approve one short script and run **one** generate.
5. Leave the page, come back, confirm the same job resumes (no second HeyGen create).
6. Play and download the MP4.
7. Confirm Settings shows Avatar IV at the configured rate and the ledger row.
8. Stop. Do not repeat generates for coverage.

---

## Definition of done (this session)

The status board is not done. The tests are not done by themselves. The homepage loading is not done.

What **is** done:

- Source, architecture, and HeyGen path were traced.
- Public auth was exercised in Cursor’s built-in browser.
- Security and missing-key behavior were checked without exposing secrets.
- A real paid-duplication risk was found and fixed in the working tree.
- Automated regressions were added and run.
- Environment blockers were separated from application defects.
- The verdict is **CONDITIONALLY READY**, not a fake 100%.
