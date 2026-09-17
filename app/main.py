"""FastAPI app entrypoint. Run with: uvicorn app.main:app --reload"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.evaluation_routes import eval_router
from app.api.observability_routes import obs_router
from app.api.routes import router
from app.evaluation.store import init_evaluation_db
from app.observability.store import init_observability_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai_analyst.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize observability and evaluation tables
    logger.info("Initializing database, observability, and evaluation tables...")
    try:
        init_observability_db()
        init_evaluation_db()
    except Exception as e:
        logger.warning("Database setup warning: %s", e)
    yield
    # Shutdown
    logger.info("Application shutting down.")


app = FastAPI(
    title="AI Analyst Agent",
    description="Natural-language database analyst backed by LangGraph, raw MCP, LangSmith Observability, and LLM Evaluation.",
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(obs_router)
app.include_router(eval_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
