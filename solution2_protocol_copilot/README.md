# Solution 2 — IQVIA Agentic Protocol Co-Pilot with Amendment-Risk Prediction

Solution 2 of the IQVIA hackathon submission. A real-time protocol editor with an agentic Amendment-Risk scoring engine that predicts which protocol clauses are most likely to require post-submission amendments, drawing on a corpus of 50 historical amendment patterns stored in pgvector and scored via Claude Sonnet 4.6. Phase 1 (this branch) stands up the full infrastructure: FastAPI + LangGraph backend, React + TipTap frontend, Postgres+pgvector — verified end-to-end before the scoring agent is wired on top in Phase 2.

---

## Prerequisites

- **Docker Postgres+pgvector** running locally:
  - Host: `localhost:5432`, Database: `vectordb`, User: `admin`, Password: `password`
  - Verify: `docker ps` should show a running postgres container with pgvector
- **Node.js** ≥ 20 with **pnpm** (`npm install -g pnpm`)
- **uv** (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Python** 3.11

---

## Backend Setup

```bash
cd solution2_protocol_copilot/backend

# 1. Copy environment template (fill in Azure creds on office laptop)
cp .env.example .env

# 2. Install dependencies
uv sync

# 3. Create tables + seed demo protocol and amendment patterns
python -m app.db.seed

# 4. Verify the environment
python scripts/verify_setup.py

# 5. Start the backend (port 8002)
uv run uvicorn app.main:app --reload --port 8002
```

**Smoke test:**
```bash
curl http://localhost:8002/health
# → {"status":"ok","llm_mode":"mock"}

curl http://localhost:8002/protocols/DIABETES-2026-PH3
# → full protocol JSON
```

---

## Frontend Setup

```bash
cd solution2_protocol_copilot/frontend

pnpm install
pnpm dev
# → Vite dev server at http://localhost:5173
```

Open http://localhost:5173 in a browser. You should see:
- Navy top bar (IQVIA · Protocol Co-Pilot)
- Gray status bar (AMENDMENT RISK: — / 0 HIGH · 0 MED · 0 LOW)
- Left panel: the ~3000-word diabetes protocol rendered in TipTap
- Right panel: "Select a clause to see its risk analysis" placeholder

---

## Environment Verification

```bash
cd solution2_protocol_copilot/backend
python scripts/verify_setup.py
```

Checks with ✓/✗ output:
1. Postgres reachable
2. pgvector extension present
3. All three tables exist
4. Seed data loaded (5 patterns, 1 protocol)
5. Azure connectivity (only if `LLM_MODE=live`)

---

## LLM Modes

Set `LLM_MODE` in `.env`:

| Mode | Description |
|------|-------------|
| `mock` | Template fallback strings, zero Azure calls. Default. |
| `fake` | Deterministic realistic stubs, no Azure. For UI dev. |
| `cached` | Replay previously captured real responses (Phase 2). |
| `live` | Real Azure OpenAI calls (requires creds in `.env`). |

**Phase 1 runs entirely in `mock` mode.** No Azure credentials required.

---

## Phase Status

- **Phase 1 (this branch):** Infrastructure only. Full stack running, protocol rendered, no scoring.
- **Phase 2 (next):** 50-pattern corpus, embeddings, Amendment-Risk agent, real-time clause scoring, risk margin decorations.
- **Phase 3+:** Mode toggle UI, suggest-fix flow, issue detail panel, export.

---

## Architecture Notes

- Backend port: **8002** (Solution 1 used 8001)
- Frontend proxy: `/api/*` → `http://localhost:8002/*` (strips `/api` prefix)
- DB: SQLAlchemy async (`asyncpg`) + raw SQL for vector ops
- Vector search: exact cosine (`<=>`), no index — deterministic at 50 rows
- Embeddings: `text-embedding-3-small` (1536-dim) — null until Phase 2 populates them
- Alembic scaffolded but Phase 1 uses `Base.metadata.create_all` via `init_db()` on startup
