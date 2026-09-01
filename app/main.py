"""FastAPI app entrypoint. Run with: uvicorn app.main:app --reload"""
from __future__ import annotations

import logging

from fastapi import FastAPI

from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="AI Analyst Agent",
    description="Natural-language database analyst backed by LangGraph + raw MCP.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
