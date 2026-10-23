import time
import uuid

import sentry_sdk
import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import get_settings

settings = get_settings()
structlog.configure(processors=[structlog.processors.TimeStamper(fmt="iso"), structlog.processors.JSONRenderer()])
log = structlog.get_logger()
if settings.sentry_dsn:
    sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment, send_default_pii=False, traces_sample_rate=.05)

app = FastAPI(title="SportPredict AI", version="0.1.0", description="Football intelligence. Demo data is explicitly simulated. No wagering endpoints.")
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT"], allow_headers=["Content-Type", "X-CSRF-Token"])


@app.middleware("http")
async def observe(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start = time.monotonic()
    try:
        response = await call_next(request)
    except Exception as exc:
        sentry_sdk.capture_exception(exc)
        log.error("request.failed", request_id=request_id, error_type=type(exc).__name__)
        response = JSONResponse({"detail": "Service error", "request_id": request_id}, status_code=500)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    log.info("request.completed", request_id=request_id, method=request.method, path=request.url.path,
             status=response.status_code, duration_ms=round((time.monotonic() - start) * 1000))
    return response


app.include_router(router)
