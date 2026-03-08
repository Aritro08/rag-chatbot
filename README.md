# LangGraph RAG App

This project includes:
- FastAPI backend (`main.py`)
- Streamlit frontend (`streamlit_app.py`)
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
- `API_BASE_URL`
- `CORS_ORIGINS`

## 2. Install Dependencies

```bash
uv sync
```

or

```bash
pip install -e .
```

## 3. Run Locally

Start FastAPI:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Start Streamlit:

```bash
streamlit run streamlit_app.py --server.port 8501 --server.address 0.0.0.0
```

By default the UI points to `http://localhost:8000`. Override with `API_BASE_URL`.

## 4. Deploy Externally

Recommended architecture:
- Deploy FastAPI as one service
- Deploy Streamlit as another service
- Set `API_BASE_URL` in Streamlit to your FastAPI public URL
- Set `CORS_ORIGINS` in FastAPI to your Streamlit URL

## 5. Supabase and Vector Storage

Supabase Postgres supports vectors through the `pgvector` extension.

Current project state:
- metadata is stored in Supabase Postgres
- embeddings are stored in Supabase Postgres (`rag_vector_chunks` table with `vector(1536)`)

On startup, the app ensures:
- `vector` extension exists
- vector chunk table and indexes exist

## 6. Run with Docker

Build and run both services:

```bash
docker compose up --build
```

Services:
- FastAPI: `http://localhost:8000`
- Streamlit: `http://localhost:8501`

Notes:
- `docker-compose.yml` loads `.env` for both services
- Streamlit is configured to call API at `http://api:8000` inside Docker network
- Keep `CORS_ORIGINS` aligned with your deployed UI domain

## 7. Health Check

FastAPI exposes:

```http
GET /health
```

Use this endpoint for deployment health probes.
