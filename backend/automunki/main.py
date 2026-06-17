import asyncio
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from automunki.api.routes.audit import router as audit_router
from automunki.api.routes.auth import router as auth_router
from automunki.api.routes.auth import users_router
from automunki.api.routes.autopkg import router as autopkg_router
from automunki.api.routes.catalogs import router as catalogs_router
from automunki.api.routes.enroll import router as enroll_router
from automunki.api.routes.icons import router as icons_router
from automunki.api.routes.insights import router as insights_router
from automunki.api.routes.manifests import router as manifests_router
from automunki.api.routes.munki_upload import router as munki_upload_router
from automunki.api.routes.pkginfo import router as pkginfo_router
from automunki.api.routes.promotion_channels import router as promotion_channels_router
from automunki.api.routes.rbac import router as rbac_router
from automunki.api.routes.repo import router as repo_router
from automunki.api.routes.reports import router as reports_router
from automunki.api.routes.settings import router as settings_router
from automunki.api.routes.workflow import router as workflow_router
from automunki.core.config import settings
from automunki.core.middleware import RequestIDMiddleware
from automunki.core.rbac_middleware import RBACMiddleware
from automunki.core.repo_basic_auth_middleware import RepoBasicAuthMiddleware

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer() if settings.debug else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(0),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("automunki_starting", version="0.1.0")
    stop = asyncio.Event()
    ticker_task: asyncio.Task | None = None
    if settings.scheduler_enabled:
        from automunki.services.autopkg_schedule import scheduler_loop

        ticker_task = asyncio.create_task(scheduler_loop(stop))
    yield
    stop.set()
    if ticker_task is not None:
        ticker_task.cancel()
        try:
            await ticker_task
        except asyncio.CancelledError:
            pass
    logger.info("automunki_shutting_down")


app = FastAPI(
    title="Munki Manager API",
    description="Munki and AutoPkg web management platform",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

app.add_middleware(RequestIDMiddleware)
app.add_middleware(RepoBasicAuthMiddleware)
app.add_middleware(RBACMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_prefix = "/api/v1"
app.include_router(auth_router, prefix=api_prefix)
app.include_router(users_router, prefix=api_prefix)
app.include_router(rbac_router, prefix=api_prefix)
app.include_router(pkginfo_router, prefix=api_prefix)
app.include_router(icons_router, prefix=api_prefix)
app.include_router(catalogs_router, prefix=api_prefix)
app.include_router(promotion_channels_router, prefix=api_prefix)
app.include_router(workflow_router, prefix=api_prefix)
app.include_router(manifests_router, prefix=api_prefix)
app.include_router(munki_upload_router, prefix=api_prefix)
app.include_router(autopkg_router, prefix=api_prefix)
app.include_router(reports_router, prefix=api_prefix)
app.include_router(audit_router, prefix=api_prefix)
app.include_router(insights_router, prefix=api_prefix)
app.include_router(settings_router, prefix=api_prefix)
app.include_router(enroll_router, prefix=api_prefix)

app.include_router(repo_router)


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "local_runner_configured": bool(settings.local_runner_token),
    }


@app.get("/ready")
async def ready():
    from fastapi.responses import JSONResponse
    from sqlalchemy import text

    from automunki.core.db import engine

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not_ready"})
