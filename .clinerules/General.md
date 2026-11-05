## Environment & Tech Stack
- Python 3.11+. Type hints everywhere.
- Web framework: FastAPI (strictly async/await).
- ORM: SQLAlchemy 2.0 with async sessions (`AsyncSession`).
- Data Validation: Pydantic v2.
- Containerization: Docker & docker-compose.

## Project Structure
- API routes in `/routers/` (webhooks, operator UI, health).
- Business logic in `/services/` (LLM providers, RAG, helpdesk client).
- Database models in `/models.py`. Pydantic schemas in `/schemas.py`.
- Frontend: Single-file Jinja2/HTML template in `templates/operator.html`.
- Knowledge base seed data in `data/kb_articles.json`.

## Coding Style & Standards
- Write complete, production-ready code. Never use `TODO`, `pass`, or dummy function placeholders.
- Table creation: Initialize database schema on startup inside FastAPI `lifespan` via `Base.metadata.create_all`.

## Task Execution Workflow
- When adding an endpoint, define the Pydantic schema in `/schemas.py` first.
- Always implement logic in order: DB Models -> Schemas -> Services -> Routers -> UI.
- Verify system health via `GET /health` (must return `200 OK`).