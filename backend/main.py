from __future__ import annotations
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
 
from config import BACKEND_DIR, REPO_ROOT, settings
from database import close_pool, create_pool

from routers import auth, documents, xray, cases, qa, search, brief, contradictions, moot
# from routers import contradictions, moot


@asynccontextmanager
async def lifespan(_: FastAPI):
    await create_pool()
    yield
    await close_pool()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.API_VERSION,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(cases.router)
app.include_router(documents.router)
app.include_router(search.router)
app.include_router(xray.router)
app.include_router(qa.router)
app.include_router(contradictions.router)
app.include_router(brief.router)
app.include_router(moot.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"name": settings.APP_NAME, "docs": "/api/docs", "health": "/health"}
