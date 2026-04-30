import logging

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-20s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)

from routers import jobs, analyze, cv  # noqa: E402  (load .env before services read it)

app = FastAPI(title="SeekJobs API", redirect_slashes=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router, prefix="/api")
app.include_router(analyze.router, prefix="/api")
app.include_router(cv.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
