# Mission Control

VantageClaw fork of abhi1693/openclaw-mission-control. Separate git repo (not a submodule).

## Remotes
- `origin` — upstream (abhi1693/openclaw-mission-control)
- `fork` — our fork (chimichangamonster/openclaw-mission-control)
- Push to `fork`, not `origin`

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

## Chat & Gateway Session Endpoints
- `GET /gateways/sessions` — list gateway sessions (requires board_id)
- `GET /gateways/sessions/{id}/history` — fetch chat history for a session
- `POST /gateways/sessions/{id}/message` — send a message into a session (supports optional `attachments` array for file references)
- `POST /gateways/sessions/{id}/upload` — upload a file for chat attachment (multipart, max 10MB, images/PDF/text/CSV/JSON/DOCX/XLSX)
- `POST /gateways/sessions/{id}/abort` — stop an agent's in-progress response
- `POST /gateways/sessions/{id}/compact` — summarise and trim session history
- `POST /gateways/sessions/{id}/reset` — clear session conversation history
- `GET/PUT /memory/files/{filename}` — read/write agent memory files (SOUL.md, IDENTITY.md, etc.) — org-scoped via `resolve_org_workspace()`
- Frontend chat page at `/chat` — single-conversation interface with The Claw, auto-resolves session, file upload (paperclip + paste), SSE real-time typing indicators with fallback polling, markdown rendering, context meter, abort/compact/clear controls
- Frontend memory page at `/memory` — view/edit agent memory files per org

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

## Environment Variables (mc-backend)
- `OPENROUTER_API_KEY` — required for cost tracking page (added to docker-compose.mission-control.yml)
- `GATEWAY_WORKSPACES_ROOT` — parent directory for per-org gateway workspaces (e.g., `/app/gateway-workspaces`)
- `GATEWAY_WORKSPACE_PATH` — legacy single-workspace fallback (e.g., `/app/gateway-workspace`)
- `DATABASE_URL`, `LOCAL_AUTH_TOKEN`, `ENCRYPTION_KEY` — standard config in .env.production

## Build & Deploy
- NEVER build on VPS (OOM). Build locally, transfer images.
- Backend: `docker build -t mc-backend -f backend/Dockerfile .`
- Frontend: `docker build -t mc-frontend --build-arg NEXT_PUBLIC_API_URL=http://vantageclaw.basa-dab.ts.net:8000 --build-arg NEXT_PUBLIC_AUTH_MODE=local -f frontend/Dockerfile frontend/`
- After deploy: `docker compose -f docker-compose.prod.yml -f docker-compose.mission-control.yml --env-file .env.production up -d mc-backend mc-frontend`
