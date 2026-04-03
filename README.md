# LangGraph RAG App

This project includes:
- FastAPI backend (`main.py`)
- Next.js frontend (`frontend/`)
- Supabase Postgres for chat/document metadata and vector embeddings (`pgvector`)

## 1. Environment Variables

Create `.env` from `.env.example` and fill values:

```bash
cp .env.example .env
```

Required values:
- `OPENAI_API_KEY`
- `SUPABASE_DB_URL` (or `DATABASE_URL`)

Optional values:
- `TAVILY_API_KEY`
- `FASTAPI_BASE_URL` (Next.js server routes -> FastAPI)
- `CORS_ORIGINS`

## 2. Install Dependencies

Python dependencies:

```bash
uv sync
```

or

```bash
pip install -e .
```

Next.js dependencies:

```bash
cd frontend
npm install
```

## 3. Run Locally

Start FastAPI:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Start Next.js frontend:

```bash
cd frontend
npm run dev
```

URLs:
- FastAPI: `http://localhost:8000`
- Next.js: `http://localhost:3000`

## 4. API Surface Used by the Next Frontend

Next.js proxies browser calls to FastAPI via route handlers under `frontend/app/api/*`:
- `POST /api/chat` -> `POST /chat`
- `POST /api/chat/stream` -> `POST /chat/stream` (SSE passthrough)
- `GET /api/chat-sessions` -> `GET /chat-sessions`
- `GET /api/chat-sessions/:id` -> `GET /chat-sessions/:id`
- `GET /api/list-docs` -> `GET /list-docs`
- `POST /api/upload-doc` -> `POST /upload-doc`
- `POST /api/delete-doc` -> `POST /delete-doc`

## 5. Deploy Externally (Render-Friendly)

Recommended architecture:
- Deploy FastAPI and frontend as separate services
- Set `FASTAPI_BASE_URL` for the frontend service to your FastAPI internal/public URL
- Keep `CORS_ORIGINS` set for any browser-direct clients (for proxy-only frontend traffic, CORS pressure is lower)

## 6. Supabase and Vector Storage

Supabase Postgres supports vectors through the `pgvector` extension.

Current project state:
- metadata is stored in Supabase Postgres
- embeddings are stored in Supabase Postgres (`rag_vector_chunks` table with `vector(1536)`)

On startup, the app ensures:
- `vector` extension exists
- vector chunk table and indexes exist

## 7. Run with Docker

Build and run:

```bash
docker compose up --build
```

Services:
- FastAPI: `http://localhost:8000`
- Next.js frontend: `http://localhost:3000`

## 8. Frontend Tests

Run frontend unit tests:

```bash
cd frontend
npm run test
```

Current test coverage includes:
- SSE event stream parsing (`token`, `done`, `error`)
- API client error normalization and backend error propagation

Manual parity and release validation checklist:
- `frontend/docs/parity-checklist.md`

## 9. Health Check

FastAPI exposes:

```http
GET /health
```

Use this endpoint for deployment health probes.
