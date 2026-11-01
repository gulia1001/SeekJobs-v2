import asyncio
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-20s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("seekjobs")

from routers import jobs, analyze, cv  # noqa: E402  (load .env before services read it)
from services.data_loader import load_jobs  # noqa: E402

# Comma-separated list of sites allowed to call the API from a browser.
CORS_ORIGINS = [
    o.strip()
    for o in (os.getenv("CORS_ORIGINS") or "http://localhost:3001,http://127.0.0.1:3001").split(",")
    if o.strip()
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # load the job dataset once at startup instead of on the first user's request
    df = await asyncio.to_thread(load_jobs)
    log.info("Jobs loaded: %d  |  CORS origins: %s", len(df), CORS_ORIGINS)
    yield


app = FastAPI(title="SeekJobs API", lifespan=lifespan, redirect_slashes=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

app.include_router(jobs.router, prefix="/api")
app.include_router(analyze.router, prefix="/api")
app.include_router(cv.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
