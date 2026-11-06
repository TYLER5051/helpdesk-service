# Helpdesk Service

AI helpdesk assistant: receives support tickets via webhook, generates a draft reply with RAG + LLM, lets an operator approve/reject it in a web UI, then delivers it back to the helpdesk. Idempotent ingestion and at-most-once delivery.

## Tech Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.12, FastAPI (async), Pydantic v2 |
| Database | PostgreSQL 15, SQLAlchemy 2.0 (async) + asyncpg |
| LLM | OpenRouter, with built-in Mock fallback |
| Frontend | Single-file Jinja2 template + vanilla JS |
| Run | Docker & Docker Compose (`web` + `db`) |

## Key Features

- **Fast webhook** — responds in ~10–25 ms; drafting (RAG + LLM) runs in a background task.
- **Idempotent** — duplicate `event_id` events are silently ignored (race-safe).
- **At-most-once delivery** — row-locked approve + `SENDING` guard; only a 200/201 marks `SENT` (5xx/timeouts retried, then back to `DRAFTED`, never double-sent).
- **Resilient** — OpenRouter 401/429/5xx/timeout/parse errors fall back to `MockLLMProvider`; works with no API key.

## Project Structure

```
app/
  main.py          FastAPI app, lifespan (table creation), routers
  config.py        Settings from env (DATABASE_URL, OPENROUTER_API_KEY)
  database.py      Async engine, session factory, get_db(), init_db()
  models.py        WebhookEvent, Ticket
  schemas.py       Pydantic schemas
  routers/         health.py, webhooks.py, operator.py
  services/        rag.py, llm.py, helpdesk.py
  data/kb_articles.json   Seed knowledge-base articles
  templates/operator.html Operator UI
  docker-compose.yml, Dockerfile, .env.example, requirements.txt
```

## Quick Start (Docker)

```bash
git clone <repo-url> helpdesk-service
cd helpdesk-service
cp .env.example .env   # defaults already match docker-compose
docker compose up --build
```

Then open http://localhost:8000/operator (API docs at `/docs`).

> Stale DB credentials from an older setup? `docker compose down -v && docker compose up --build`.

## Run Locally (optional)

```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Requires a reachable PostgreSQL (default: `postgresql+asyncpg://postgres:postgres@localhost:5432/helpdesk_db`).

## Configuration (.env)

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@db:5432/helpdesk_db` | Postgres connection for the `web` container |
| `OPENROUTER_API_KEY` | *(empty)* | Empty → Mock mode, no external LLM calls |

Config is read once at startup — restart to apply changes.

## API

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness probe |
| POST | `/webhooks/helpdesk` | Ingest a ticket (idempotent by `event_id`) |
| GET | `/operator` | Operator UI |
| GET | `/api/operator/tickets` | Tickets, newest first |
| POST | `/api/operator/tickets/{id}/approve` | Deliver approved draft via `reply_url` |
| POST | `/api/operator/tickets/{id}/reject` | Reject draft; nothing is sent |

## Example Webhook

```bash
curl -X POST http://localhost:8000/webhooks/helpdesk \
  -H "Content-Type: application/json" \
  -d '{"event_id":"evt-0001","ticket_id":"TKT-0001","customer_email":"customer@example.com","message":"I forgot my password and cannot log in.","reply_url":"https://helpdesk.example.com/api/tickets/TKT-0001/replies"}'
```

→ `{"status":"accepted","ticket_id":"TKT-0001"}`. A draft appears in the operator UI within 5–30 s (Mock) for review.
Re-sending the same `event_id` → `{"status":"duplicate_ignored"}`.

## Ticket Lifecycle

```
PENDING ──(background RAG+LLM)──► DRAFTED ──► SENDING ──► SENT
                                       │            └─ retries fail → DRAFTED (retryable)
                                       └─ REJECTED (operator)
```

## Notes

- Knowledge base seed: `data/kb_articles.json` (keyword match; restart after edits).
- Operator UI auto-refreshes every 8 s.
