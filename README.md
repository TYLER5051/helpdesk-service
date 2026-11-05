# Helpdesk Service

An AI-powered helpdesk assistant that ingests support tickets via webhook, retrieves relevant knowledge-base articles (RAG), and generates draft replies with a Large Language Model (OpenRouter). A human operator reviews and approves each draft through a simple web UI before the reply is delivered back to the helpdesk — with idempotent ingestion and at-most-once delivery guarantees.

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Web framework | FastAPI (fully async/await) |
| ORM | SQLAlchemy 2.0 (async) + asyncpg |
| Database | PostgreSQL 15 |
| Orchestration | Docker & Docker Compose (`web` + `db`) |
| LLM | OpenRouter (Gemini / Gemma free tier) with a built-in Mock mode |
| Frontend | Single-file Jinja2 template + vanilla JavaScript |
| Validation | Pydantic v2 |

## Architecture Highlights

### Fast webhook ingestion (SLA < 200 ms)
The webhook endpoint only performs the work required to guarantee persistence — it stores a `WebhookEvent` and a `Ticket` (status `PENDING`), schedules `process_ticket_background(ticket_id)` via FastAPI `BackgroundTasks`, and immediately returns `200 OK`. All slow work (RAG retrieval + LLM draft generation) happens off the request path in a separate database session. Measured response time is ~10–25 ms.

### Idempotency & deduplication by `event_id`
Every webhook is deduplicated on the unique `event_id` column (`webhook_events.event_id` has a unique index). A stored event short-circuits the request with `{"status": "duplicate_ignored"}`. A race-safe `IntegrityError` guard turns even simultaneous duplicate deliveries into a no-op instead of a `500`.

### At-Most-Once reply delivery
`send_ticket_reply()` reads the ticket with `SELECT ... FOR UPDATE` and refuses to send anything that is not a `DRAFTED` ticket without a `sent_at` timestamp. The status is flipped to `SENDING` (committed before any network I/O), and only a 200/201 response from the helpdesk moves the ticket to `SENT` + `sent_at`. 5xx responses, timeouts, and transport errors are retried (3 attempts with backoff) and then leave the ticket back in `DRAFTED` — never `SENT`, never double-delivered.

### LLM fallback to Mock mode
If `OPENROUTER_API_KEY` is empty — or the OpenRouter API fails — the service automatically falls back to `MockLLMProvider`, which simulates a real LLM delay (5–30 s) and returns a plausible draft. The service is therefore fully functional and testable without any external API key.

## Project Structure

```
helpdesk-service/
├── app/
│   ├── main.py               # FastAPI app, lifespan (table creation), router registration
│   ├── config.py             # Settings from environment (DATABASE_URL, OPENROUTER_API_KEY)
│   ├── database.py           # Async engine, async_sessionmaker, get_db(), init_db()
│   ├── models.py             # SQLAlchemy models: WebhookEvent, Ticket, KnowledgeArticle
│   ├── schemas.py            # Pydantic v2 schemas: WebhookPayload, HelpdeskReplyPayload, TicketResponse
│   ├── routers/
│   │   ├── health.py         # GET /health
│   │   ├── webhooks.py       # POST /webhooks/helpdesk (idempotent, BackgroundTasks)
│   │   └── operator.py       # Operator UI pages + ticket moderation API
│   └── services/
│       ├── rag.py            # Knowledge-base retrieval
│       ├── llm.py            # OpenRouter / Mock LLM providers + generate_draft_reply()
│       └── helpdesk.py       # Background drafting + at-most-once reply delivery
├── data/
│   └── kb_articles.json      # Seed knowledge-base articles
├── templates/
│   └── operator.html         # Operator moderation UI
├── docker-compose.yml        # web + PostgreSQL 15 services
├── Dockerfile
├── .env.example              # Environment template (cp .env.example .env)
└── requirements.txt
```

## How to Run

### Prerequisites
- Docker Engine with Docker Compose v2.

### 1. Clone and configure
```bash
git clone <repo-url> helpdesk-service
cd helpdesk-service
cp .env.example .env
```

The default values in `.env.example` already match the docker-compose services, so a bare `cp` works out of the box. Two knobs are available:

| Variable | Description |
|---|---|
| `DATABASE_URL` | Postgres connection string for the `web` container. Default: `postgresql+asyncpg://postgres:postgres@db:5432/helpdesk_db`. |
| `OPENROUTER_API_KEY` | OpenRouter API key, e.g. `sk-or-v1-...`. **Leave empty to run in Mock mode** (no external LLM calls). |

### 2. Start the stack
```bash
docker compose up --build
```

- The `db` service initializes PostgreSQL (user `postgres`, database `helpdesk_db`) and is health-checked before the app starts.
- The `web` service installs dependencies, and on startup creates all database tables automatically (SQLAlchemy `create_all` inside the FastAPI `lifespan`).

> **Existing volumes:** if you previously ran an older version of this project, the `postgres_data` volume may hold stale credentials. Reset it once:
> `docker compose down -v && docker compose up --build`

### 3. Useful links
| Service | URL |
|---|---|
| Healthcheck | http://localhost:8000/health |
| Webhook | http://localhost:8000/webhooks/helpdesk |
| Operator UI | http://localhost:8000/operator |
| OpenAPI docs (Swagger) | http://localhost:8000/docs |
| PostgreSQL | `localhost:5432` (database `helpdesk_db`) |

### Running locally without Docker (optional)
```bash
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload       # OpenRouter Mock mode unless OPENROUTER_API_KEY is set
```
Requires a reachable PostgreSQL instance; the default local connection URL is `postgresql+asyncpg://postgres:postgres@localhost:5432/helpdesk_db`.

## cURL examples

### 1. Send a test webhook

```bash
curl -X POST http://localhost:8000/webhooks/helpdesk \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "evt-20261105-0001",
    "ticket_id": "TKT-20261105-0001",
    "customer_email": "customer@example.com",
    "message": "I forgot my password and cannot log in.",
    "reply_url": "https://helpdesk.example.com/api/tickets/TKT-20261105-0001/replies"
  }'
```

Expected response (returned immediately, SLA < 200 ms):

```json
{"status":"accepted","ticket_id":"TKT-20261105-0001"}
```

The background task then drafts a reply (5–30 s in Mock mode). Open http://localhost:8000/operator to review it and approve/reject.

### 2. Verify idempotency (replay the same webhook)

Re-send the request above unchanged. Because `event_id` is already stored, the service ignores the duplicate:

```bash
curl -X POST http://localhost:8000/webhooks/helpdesk \
  -H "Content-Type: application/json" \
  -d '{"event_id":"evt-20261105-0001","ticket_id":"TKT-20261105-0001","customer_email":"customer@example.com","message":"I forgot my password and cannot log in.","reply_url":"https://helpdesk.example.com/api/tickets/TKT-20261105-0001/replies"}'
```

Expected response:

```json
{"status":"duplicate_ignored"}
```

> Note: the `reply_url` above is a placeholder. In real usage the helpdesk provider supplies the callback URL where the approved reply is delivered via `POST` with the `HelpdeskReplyPayload` body `{"ticket_id": "...", "message": "..."}`.

## API Reference

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness probe; always returns `200 OK` with `{"status": "ok"}`. |
| POST | `/webhooks/helpdesk` | Ingest a new helpdesk ticket (idempotent by `event_id`). |
| GET | `/operator` | Operator moderation UI (HTML page). |
| GET | `/api/operator/tickets` | All tickets as JSON, newest first. |
| POST | `/api/operator/tickets/{ticket_id}/approve` | Send the approved draft reply to the helpdesk (`reply_url`). |
| POST | `/api/operator/tickets/{ticket_id}/reject` | Reject the draft; nothing is delivered. |

## Ticket Lifecycle

```
             (background task: RAG + LLM)
PENDING ────────────────────────────────► DRAFTED ──► SENDING ──► SENT
                                                  │        └──► DRAFTED  (on 5xx / timeout after retries — retryable)
                                                  └──► REJECTED (operator decision; nothing is sent)
```

## Operational Notes

- **Configuration is read once at startup** (`get_settings()` is cached). Changing `OPENROUTER_API_KEY` or `DATABASE_URL` requires a service restart.
- **Knowledge base** — seed articles live in `data/kb_articles.json`. RAG retrieval uses keyword matching over the installed articles; queries in other languages fall back to the top articles for now.
- **Drafting is background** — a webhook gets a reply within 5–30 s in Mock mode, or after however long the OpenRouter call takes. The operator UI polls `/api/operator/tickets` and auto-refreshes every 8 seconds.
