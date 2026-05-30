from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.session import init_db
from app.routers import health, protocols, score, fixes, feasibility, drafting
from app.config import settings

app = FastAPI(title="Protocol Co-Pilot API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:5174", "http://localhost:5176"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(protocols.router)
app.include_router(score.router)
app.include_router(fixes.router)
app.include_router(feasibility.router)
app.include_router(drafting.router)


@app.on_event("startup")
async def startup():
    await init_db()
