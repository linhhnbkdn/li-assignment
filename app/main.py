from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.routes import search
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.rate_limiter import SlidingWindowRateLimiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(level=settings.log_level)
    app.state.rate_limiter = SlidingWindowRateLimiter(
        limit=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window,
    )
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="HR Employee Search API",
        description="Search directory for HR organizations",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(search.router, prefix="/api/v1")
    return app


app = create_app()
