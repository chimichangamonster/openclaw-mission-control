# Mission Control

Fork of abhi1693/openclaw-mission-control. Separate git repo (not a submodule).

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

## Environment Variables (mc-backend)
- `OPENROUTER_API_KEY` — required for cost tracking page (added to docker-compose.mission-control.yml)
- `DATABASE_URL`, `LOCAL_AUTH_TOKEN`, `ENCRYPTION_KEY` — standard config in .env.production

## Build & Deploy
- NEVER build on VPS (OOM). Build locally, transfer images.
- Backend: `docker build -t mc-backend -f backend/Dockerfile .`
- Frontend: `docker build -t mc-frontend --build-arg NEXT_PUBLIC_API_URL=http://100.100.202.83:8000 --build-arg NEXT_PUBLIC_AUTH_MODE=local -f frontend/Dockerfile frontend/`
- After deploy: `docker compose -f docker-compose.prod.yml -f docker-compose.mission-control.yml --env-file .env.production up -d mc-backend mc-frontend`
