"""
FastAPI application entry point.

Run with: uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.flow import router

app = FastAPI(
    title="Policy Visualizer API",
    version="3.0.1",
    description="Converts a network policy XML service export into a Flow IR diagram.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:80"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
