from datetime import datetime, timezone

from sqlalchemy import select

from .celery_app import celery_app
from .config import settings
from .db import SessionLocal
from .models import OutboxEvent, OutboxStatus


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def publish_pending_outbox() -> int:
    published = 0

    with SessionLocal() as db:
        while published < settings.outbox_batch_size:
            event = db.scalar(
                select(OutboxEvent)
                .where(
                    OutboxEvent.status == OutboxStatus.PENDING,
                    OutboxEvent.available_at <= utcnow(),
                )
                .order_by(OutboxEvent.id)
                .with_for_update(skip_locked=True)
            )

            if not event:
                break

            try:
                celery_app.send_task(
                    "notification.process_delivery",
                    args=[str(event.delivery_id)],
                )
                event.status = OutboxStatus.PUBLISHED
                event.published_at = utcnow()
                event.attempts += 1
                event.last_error = None
                db.commit()
                published += 1
            except Exception as exc:
                event.attempts += 1
                event.last_error = str(exc)[:4000]
                db.commit()
                # Do not spin forever when Redis is down.
                break

    return published
