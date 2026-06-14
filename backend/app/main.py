import logging
import traceback
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from app.database import init_db
from app.routes import portfolio, stocks, watchlist as watchlist_router, recommendations as rec_router, intel as intel_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Database ready")
    yield


app = FastAPI(title="Local Stock Analyzer", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(portfolio.router)
app.include_router(stocks.router)
app.include_router(watchlist_router.router)
app.include_router(rec_router.router)
app.include_router(intel_router.router)


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    logger.error("Unhandled error on %s %s\n%s", request.method, request.url.path, traceback.format_exc())
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/")
def root():
    return {"status": "ok"}
