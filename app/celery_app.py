from celery import Celery

from .config import settings


celery_app = Celery(
    "notification_service",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    beat_schedule={
        "publish-outbox": {
            "task": "notification.publish_outbox",
            "schedule": settings.outbox_publish_interval_seconds,
        },
        "reap-stale-deliveries": {
            "task": "notification.reap_stale_deliveries",
            "schedule": settings.reaper_interval_seconds,
        },
    },
)
