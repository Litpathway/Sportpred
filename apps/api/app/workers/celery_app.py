from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()
celery = Celery("sportpredict", broker=settings.redis_url, backend=settings.redis_url, include=["app.workers.tasks"])
celery.conf.update(
    task_serializer="json", result_serializer="json", accept_content=["json"], timezone="UTC", enable_utc=True,
    task_acks_late=True, task_reject_on_worker_lost=True, worker_prefetch_multiplier=1,
    task_soft_time_limit=780, task_time_limit=840, result_expires=86400, broker_connection_retry_on_startup=True,
    beat_schedule={
        "pipeline-every-15-minutes": {"task": "sportpredict.run_job", "schedule": crontab(minute="*/15"), "args": ["pipeline"]},
        "code-monitor-every-5-minutes": {"task": "sportpredict.run_job", "schedule": crontab(minute="*/5"), "args": ["monitor"]},
        "drift-daily": {"task": "sportpredict.run_job", "schedule": crontab(hour=3, minute=0), "args": ["drift"]},
    },
)
