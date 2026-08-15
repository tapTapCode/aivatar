# UI/UX implementation summary

Date: 2026-08-15 (Asia/Manila)

## Goal

Give Exact Scene a first-party **production workspace** so operators can inspect health, projects, jobs, queue state, and labelled cost estimates without using only curl/OpenAPI. ClipNET UI was not reused.

## Pages created

| Route (in-app) | Purpose | Backend |
| --- | --- | --- |
| Overview | Counts, health/ready, recent jobs, metric snippets | `/health`, `/ready`, `/v1/*`, `/metrics` |
| Projects | Project script catalog, edit, and approval | `GET/PUT /v1/projects`, `POST /v1/projects/{id}/approve` |
| Videos | Job table + production workspace timeline | `GET /v1/videos`, cancel |
| Queue | Grouped queued / running / failed / completed | Same list API |
| Cost & capacity | Live metrics + documented estimates (labelled) | `/metrics` + static evidence text |

## Current implementation

| File | Role |
| --- | --- |
| `frontend/app/page.tsx` | Single authenticated application entry |
| `frontend/components/AuthScreen.tsx` | Login, registration, recovery, and SSO UI |
| `frontend/components/Dashboard.tsx` | Shell, studio, projects, assets, jobs, and dialogs |
| `frontend/lib/api.ts` | Typed same-origin API and CSRF client |
| `src/api/main.py` | API-only FastAPI control plane |

## Components / patterns

- Persistent desktop sidebar; stacked compact nav under 900px
- Status badges with text + color (not color alone)
- Skeleton loading on overview
- Empty states with next action
- Confirm dialog before cancel
- Script draft/approve before generate
- Skip link + focus outlines
- `prefers-reduced-motion` disables shimmer

## Responsive checks (manual layout review)

| Width | Expectation |
| ---: | --- |
| 1440 | Two-column shell |
| 1024 | Two-column, tables scroll |
| 768 / 390 | Single column; nav wraps; dialog fits viewport |

Automated browser pixel tests were not run; CSS media queries cover the breakpoints above.

## Accessibility

- Skip to content link
- Dialog labelled by title
- Icon-free text buttons for primary actions
- Owner field labelled
- Alerts use `role="status"`

## Real backend connections

All job/project data comes from the live FastAPI control plane (in-memory repository in default mode). Cost dollar figures on the Cost page are **explicitly labelled estimates**, not fabricated ledger rows.

## Intentionally not built

- Research/script LLM wizard
- Google Drive / YouTube publish UI
- ClipNET navigation merge
- Fake “Generate 30-minute video” that implies GPU readiness
