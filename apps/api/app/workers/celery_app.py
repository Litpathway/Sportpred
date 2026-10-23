from celery import Celery
from celery.schedules import crontab
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.core.config import get_settings

settings = get_settings()
broker_url = settings.redis_url
parts = urlsplit(broker_url)
if parts.scheme == "rediss":
    query = dict(parse_qsl(parts.query))
    query.setdefault("ssl_cert_reqs", "required")
    broker_url = urlunsplit(parts._replace(query=urlencode(query)))
celery = Celery("sportpredict", broker=broker_url, backend=broker_url, include=["app.workers.tasks"])
celery.conf.update(
    task_serializer="json", result_serializer="json", accept_content=["json"], timezone="UTC", enable_utc=True,
    task_acks_late=True, task_reject_on_worker_lost=True, worker_prefetch_multiplier=1,
    task_soft_time_limit=780, task_time_limit=840, result_expires=86400, broker_connection_retry_on_startup=True,
    broker_transport_options={"polling_interval": 30, "health_check_interval": 60},
    beat_schedule={
        "pipeline": {"task": "sportpredict.run_job", "schedule": timedelta(minutes=settings.pipeline_interval_minutes), "args": ["pipeline"]},
        **({"code-monitor-every-5-minutes": {"task": "sportpredict.run_job", "schedule": crontab(minute="*/5"), "args": ["monitor"]}} if settings.booking_provider == "authorized" else {}),
        "drift-daily": {"task": "sportpredict.run_job", "schedule": crontab(hour=3, minute=0), "args": ["drift"]},
    },
)
