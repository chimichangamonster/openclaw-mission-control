# Mission Control

VantageClaw fork of abhi1693/openclaw-mission-control. Separate git repo (not a submodule).

## Remotes
- `origin` — our fork (chimichangamonster/openclaw-mission-control) — push here
- `upstream` — abhi1693/openclaw-mission-control — read-only, used by `make sync-upstream` if needed
- Reconfigured 2026-04-09: previously `origin`/`fork` swap, renamed so `git status` reports honest "ahead/behind" against the fork instead of phantom drift against upstream

### Upstream-sync discipline — FROZEN as of 2026-04-20

**Do not run `make sync-upstream` as a reflex.** The fork is deliberately indefinite.

VantageClaw is ~40 commits ahead of upstream and building a fundamentally different product on the same foundation (multi-tenant business platform vs. abhi1693's single-tenant mission-control). Every upstream pull is risk exposure for zero strategic benefit — dependabot bumps and small fixes upstream are not worth the merge-conflict cost or the surface-area risk of breaking load-bearing customizations.

**The rule:** upstream pulls require a deliberate decision with scoped intent. Specifically:

1. **No blanket `git merge upstream/master`.** If you want a specific upstream commit (e.g. a security patch or a specific bugfix), cherry-pick it onto a scoped branch, test it, merge to main individually.
2. **Security patches are the only routine exception.** CVE disclosure in an upstream dep → cherry-pick the fix, ship. Everything else is case-by-case.
3. **Before any upstream sync:** write what you're pulling and why in the commit message. Don't do passive "sync upstream" commits.
4. **Watch for upstream-replace-with-build decisions.** If upstream ships something we were planning to build, consider a clean reimplementation in our own architecture rather than merging — usually faster than resolving conflicts.

**Why this is now explicit:** the convenience of `make sync-upstream` as a one-command reflex is a risk. Session 2026-04-20 audited the fork state (~40 commits ahead, last sync 2026-03-24, prior sync had conflicts on `0b8d95b`). Conclusion: convert implicit discipline into explicit rule so future sessions and fresh-context collaborators don't accidentally re-open the upstream-coupling risk.

**The Makefile target stays** (removing it would hide capability we occasionally need), but it now requires deliberate invocation with intent documented in the commit.

Related: parent-repo `.openclaw-gateway/` fork (gitignored sibling) follows the same rule by analogy. If a gateway security patch ships upstream, cherry-pick it; otherwise freeze.

## Backend (Python 3.12 + FastAPI)
- Entry: `backend/app/main.py`
- Models: SQLModel in `backend/app/models/`
- Routes: `backend/app/api/` — user routes and agent routes (prefixed with `/agent/`)
- Services: `backend/app/services/` — business logic (email, polymarket, etc.)
- Auth: `AUTH_MODE=local` with single token, Clerk support exists but disabled
- DB: PostgreSQL `mission_control` database, auto-migrate on startup
- IMPORTANT: customFetch wrapper in frontend adds auth headers automatically

## Frontend (Next.js 15 + TypeScript)
- App router at `frontend/src/app/`
- API helpers in `frontend/src/lib/` (polymarket-api.ts, email-api.ts, etc.)
- Generated API client via Orval in `frontend/src/api/generated/`
- Auth check: `useAuth()` from `@/auth/clerk` — returns `isSignedIn` (always true in local mode after token entry)
- IMPORTANT: `NEXT_PUBLIC_API_URL` is baked at build time, not runtime

## Key Custom API Endpoints
- `GET/POST /paper-trading/portfolios` — portfolio CRUD
- `POST /paper-trading/portfolios/{id}/trades` — execute trade (supports stop_loss, take_profit, company_name, exchange, sector, source_report params)
- `PATCH /paper-trading/portfolios/{id}/positions/{id}` — update position price/metadata
- `PATCH /paper-trading/portfolios/{id}/auto-trade` — toggle auto-trade on/off
- `GET /paper-trading/portfolios/{id}/summary` — performance stats (includes total_fees, avg_hold_days)
- `GET /cost-tracker/usage` — OpenRouter credit balance and spending
- `GET /cost-tracker/models` — live model pricing from OpenRouter with tier classification
- `POST/GET/PATCH /paper-bets/portfolios/{id}/bets` — sports betting CRUD
- `GET/POST /watchlist/portfolios/{id}/items` — watchlist CRUD (status filter: watching/alerting/bought/all)
- `PATCH /watchlist/portfolios/{id}/items/{id}` — update price, RSI, volume, sentiment, status
- `DELETE /watchlist/portfolios/{id}/items/{id}` — remove from watchlist
- `POST /watchlist/portfolios/{id}/items/bulk` — bulk add from report scan
- `GET /watchlist/portfolios/{id}/items/summary` — counts + active alerts

## Cron Job CRUD Endpoints
- `GET /cron-jobs` — list cron jobs (RPC with file-read fallback)
- `POST /cron-jobs` — create job via gateway RPC (operator+ role)
- `PATCH /cron-jobs/{id}` — update job (operator+ role)
- `DELETE /cron-jobs/{id}` — remove job (operator+ role)
- `POST /cron-jobs/{id}/run` — trigger manual run (operator+ role)
- `GET /cron-jobs/{id}/runs` — run history (member role)
- Schemas: `app/schemas/cron_jobs.py` — `CronJobCreate`, `CronJobUpdate`, `CronRunRecord`
- Frontend: `/cron-jobs` page — create dialog, enable/disable toggle, edit, delete, run now, run history

## Model Registry & Pinning Endpoints
- `GET /models/registry` — list all known models with versions, status, pricing
- `POST /models/registry/refresh` — refresh from OpenRouter (admin role)
- `GET /models/registry/{family}/versions` — version history for a model family
- `GET /models/pins` — get per-org model pins + deprecation warnings
- `PUT /models/pins` — set pins (admin role, audit-logged)
- Service: `app/services/model_registry.py` — in-memory cache + JSON persistence
- Frontend: Model Registry & Pinning section in org-settings page

## Chat & Gateway Session Endpoints
- `GET /gateways/sessions` — list gateway sessions (requires board_id)
- `GET /gateways/sessions/{id}/history` — fetch chat history for a session
- `POST /gateways/sessions/{id}/message` — send a message into a session (supports optional `attachments` array for file references)
- `POST /gateways/sessions/{id}/upload` — upload a file for chat attachment (multipart, max 10MB, images/PDF/text/CSV/JSON/DOCX/XLSX)
- `POST /gateways/sessions/{id}/abort` — stop an agent's in-progress response
- `POST /gateways/sessions/{id}/compact` — summarise and trim session history
- `POST /gateways/sessions/{id}/reset` — clear session conversation history
- `GET/PUT /memory/files/{filename}` — read/write agent memory files (SOUL.md, IDENTITY.md, etc.) — org-scoped via `resolve_org_workspace()`
- `GET /memory/knowledge` — list compiled knowledge articles from `workspace/knowledge/` (category from subdirectory)
- `GET /memory/knowledge/{path}` — read single knowledge article (redacted)
- `GET /memory/reports` — list cron-generated reports from `workspace/reports/` (newest-first, category from filename prefix)
- `GET /memory/reports/{path}` — read single cron report (redacted)
- Frontend chat page at `/chat` — single-conversation interface with The Claw, auto-resolves session, file upload (paperclip + paste), SSE real-time typing indicators with fallback polling, markdown rendering, context meter, abort/compact/clear controls
- Frontend memory page at `/memory` — three tabs: Memory Files (editable), Knowledge Base (compiled articles), Reports (cron skill outputs)

## Contacts & Email Visibility Endpoints
- `GET/POST /contacts` — list/create org contacts (manual external contacts)
- `PATCH/DELETE /contacts/{id}` — update/delete contact
- `GET /agent/contacts/members` — list org members (name, email, role) for agent contact resolution
- `GET /agent/contacts/search?q=name` — unified search across org members, manual contacts, and email history (deduplicated, priority-sorted)
- `PATCH /email/accounts/{id}` — now supports `visibility` field ("shared" or "private")
- `PATCH /google-calendar/connections/{id}` — update calendar connection visibility
- Email accounts have `visibility` field: "shared" (default) or "private". Private accounts hidden from non-owner/non-admin users and from agents.
- Google Calendar supports multiple connections per org with same visibility model.
- `GET/POST/PATCH/DELETE /microsoft-graph/calendar/events` — Outlook Calendar CRUD (same event format as Google Calendar)
- `GET /microsoft-graph/calendar/calendars` — List Outlook calendars
- Outlook Calendar uses existing Microsoft Graph OAuth (no separate connection needed — `Calendars.ReadWrite` scope already included)

## Document Intake Endpoints
- `POST /document-intake/process` — upload document for text extraction + LLM classification (multipart, max 20MB, PDF/images/text)
- `POST /document-intake/agent/process` — agent-accessible version (same logic)
- Returns: `{filename, content_type, extracted_text, classification: {type, confidence, summary}, page_count}`
- Classification types: invoice, receipt, contract, report, field_report, purchase_order, timesheet, safety_report, permit, correspondence, other

## Email Send & Invoice Endpoints
- `POST /email/accounts/{id}/send` — standalone email send (to, subject, body, optional body_html)
- `POST /agent/email/send` — agent email send via HITL approval flow
- `POST /bookkeeping/invoices/{id}/send` — generate invoice PDF + deliver via email, WeCom, or both + mark status as "sent"
  - `delivery`: `"email"` (default), `"wecom"`, or `"both"`
  - `wecom_user_id`: required when delivery includes wecom

## WeCom Send Endpoints
- `POST /wecom/send` — send text or news (rich link card) message to WeCom user (admin-gated, content-filtered)
  - `msg_type`: `"text"` (default) or `"news"` (requires title + url)

## Environment Variables (mc-backend)
- `OPENROUTER_API_KEY` — required for cost tracking page (added to docker-compose.mission-control.yml)
- `GATEWAY_WORKSPACES_ROOT` — parent directory for per-org gateway workspaces (e.g., `/app/gateway-workspaces`)
- `DATABASE_URL`, `LOCAL_AUTH_TOKEN`, `ENCRYPTION_KEY` — standard config in .env.production

## Build & Deploy
- NEVER build on VPS (OOM). Build locally, transfer images.
- Backend: `docker build -t mc-backend -f backend/Dockerfile .`
- Frontend: `docker build -t mc-frontend --build-arg NEXT_PUBLIC_API_URL=https://app.vantageclaw.ai --build-arg NEXT_PUBLIC_AUTH_MODE=clerk --build-arg NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_... -f frontend/Dockerfile frontend/`
- After deploy: `docker compose -f docker-compose.prod.yml -f docker-compose.mission-control.yml --env-file .env.production up -d mc-backend mc-frontend`
